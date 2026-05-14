# Version: 03.14.31
# Phase: PHASE2
"""
ui/timeline_canvas.py
Timeline canvas
"""
from bisect import bisect_left, bisect_right
import math

import numpy as np
from PyQt6.QtCore import QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QSizePolicy, QScrollArea

from core.frame_time import frame_count, frame_to_sec, normalize_fps, sec_to_nearest_frame, snap_sec_to_frame

from ui.timeline.timeline_constants import (
    CANVAS_H,
    ICON_SZ,
    SEG_TOP,
    _build_gaps,
)
from ui.timeline.timeline_paint import TimelinePaintMixin
from ui.timeline.timeline_input import TimelineInputMixin
from ui.timeline.timeline_inline_edit import TimelineInlineEditMixin
from ui.timeline.segment_store import TimelineSegmentStore
from ui.gpu_rendering import accelerated_widget_base, configure_lightweight_paint, configure_opengl_widget, gpu_backend_name


TimelineCanvasBase = accelerated_widget_base("timeline")


class TimelineCanvas(TimelineInlineEditMixin, TimelineInputMixin, TimelinePaintMixin, TimelineCanvasBase):
    seg_clicked             = pyqtSignal(int, float)
    seg_right_clicked       = pyqtSignal(float, QPoint)
    stt_candidate_selected  = pyqtSignal(dict)
    seg_double_clicked      = pyqtSignal(int, float)
    seg_time_changed        = pyqtSignal(int, float, float, str)
    seg_timing_confirm_requested = pyqtSignal(list)
    seg_to_gap              = pyqtSignal(int)
    gap_activated           = pyqtSignal(float, float)
    gap_to_segs             = pyqtSignal(float, float)
    gap_generate_requested  = pyqtSignal(float, float, float, str)
    scrub_sec               = pyqtSignal(float)
    drag_preview_sec        = pyqtSignal(float)
    drag_started            = pyqtSignal()
    drag_finished           = pyqtSignal()
    step_frame              = pyqtSignal(int)
    sig_inline_text_changed = pyqtSignal(int, str)
    sig_editing_mode        = pyqtSignal(bool)
    sig_split_request       = pyqtSignal(int, float, int)
    sig_speaker_split_request = pyqtSignal(int, int)
    sig_clip_selected       = pyqtSignal(int)
    sig_clip_delete_requested = pyqtSignal(int)
    sig_clip_add_requested    = pyqtSignal()   #  : clip_idx
    playhead_menu_requested = pyqtSignal(QPoint, float)
    provisional_cut_boundary_requested = pyqtSignal(float)
    provisional_cut_boundary_delete_requested = pyqtSignal(int, float)
    diamond_merge           = pyqtSignal(int, int)
    sig_smart_split         = pyqtSignal(int, float, bool)
    sig_speech_result       = pyqtSignal(str)
    speaker_changed         = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.re_recog_zone = None
        self.re_recog_progress = None
        self.llm_review_segment: dict | None = None
        self.setMinimumHeight(CANVAS_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        configure_lightweight_paint(self, opaque=True)
        configure_opengl_widget(self, "timeline")
        self.render_backend = gpu_backend_name("timeline")
        self.focus_mode = "segment"
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self._ime_preedit = ""
        self.sig_speech_result.connect(self._on_speech_result)
        self._is_listening = False
        self._listening_line: int | None = None
        self._mic_waveform_samples: list[float] = []

        self.pps = 200.0
        self.frame_rate: float = 30.0
        self.segments:     list[dict] = []
        self.gap_segments: list[dict] = []
        self.auto_generate_gap_segments: bool = True
        self.show_gap_insert_controls: bool = True
        self.vad_segments: list[dict] = []
        self.voice_activity_segments: list[dict] = []
        self.total_duration: float = 0.0
        self.active_seg_start: float | None = None
        self.active_seg_line: int | None = None
        self.playhead_sec: float = 0.0
        self._last_playhead_px: int | None = None
        self._waveform = None
        self.boundary_times: list[float] = []
        self.scan_boundary_times: list[float] = []
        self.user_alignment_guides: list[float] = []
        self.show_scan_boundary_markers: bool = False
        self._multiclip_boxes: list[dict] = []   # 
        self._clip_delete_rects: list[tuple[int, QRect]] = []
        self._clip_add_rect = QRect()
        self._clip_add_placeholder = None  
        self._active_clip_idx: int = 0   # active clip index (init fix)
        self._hover_line:  int | None = None
        self._hover_handle: tuple | None = None
        self._hover_scan_boundary_idx: int | None = None

        self._drag_seg:   dict | None = None
        self._drag_edge:  str  | None = None
        self._drag_adj_l: dict | None = None
        self._drag_adj_r: dict | None = None
        self._drag_x0:    int  = 0
        self._drag_s0_start: float = 0.0
        self._drag_s0_end:   float = 0.0
        self._drag_adj_orig_start_l: float = 0.0
        self._drag_adj_orig_end_l:   float = 0.0
        self._drag_adj_orig_start_r: float = 0.0
        self._drag_adj_orig_end_r:   float = 0.0
        self._drag_merge_pair: tuple[int, int] | None = None

        self._snap_lines = []
        self._drag_guide_x: int | None = None
        self._drag_snap_candidate: dict | None = None
        self._is_scrubbing = False
        self._is_panning = False
        self._pending_center_drag_seg: dict | None = None
        self._pending_center_drag_x: int = 0
        self._pending_center_drag_y: int = 0

        self._edit_active   = False
        self._edit_line     = -1
        self._edit_text     = ""
        self._edit_orig     = ""
        self._edit_cursor   = 0
        self._inline_editor = None
        self._inline_editor_syncing = False
        self._inline_editor_context_menu_open = False
        self._arrow_key_hold_direction: int = 0
        self._arrow_key_hold_started_mono: float = 0.0
        self._arrow_key_hold_repeat_active: bool = False
        self._arrow_key_hold_timer = QTimer(self)
        self._arrow_key_hold_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._arrow_key_hold_timer.setInterval(90)
        self._arrow_key_hold_timer.timeout.connect(self._emit_arrow_key_hold_step)
        self._cursor_vis    = True
        self._cursor_timer  = QTimer(self)
        self._cursor_timer.setInterval(500)
        self._cursor_timer.timeout.connect(self._blink_cursor)

        self._speech_mask: np.ndarray | None = None
        self._speech_mask_wf_len: int = 0
        self._waveform_line_cache_key = None
        self._waveform_line_cache = None
        self._analysis_markers_cache_key = None
        self._analysis_markers_cache: list[dict] = []
        self._visible_analysis_markers_cache_key = None
        self._visible_analysis_markers_cache: list[dict] = []
        self._visible_voice_activity_cache_key = None
        self._visible_voice_activity_cache: list[dict] = []
        self._visible_segment_lanes_cache_key = None
        self._visible_segment_lanes_cache: dict[str, object] = {}
        self._roughcut_major_cache_key = None
        self._roughcut_major_cache: list[dict] = []
        self._render_epoch = 0
        self._paint_index_cache: dict[str, dict] = {}
        self._paint_last_visible_counts: dict[str, int] = {}
        self._segment_store: TimelineSegmentStore | None = None
        self._segment_store_geometry_signature = None
        self._segment_visual_style_cache: dict[tuple, tuple[str, str]] = {}
        self._line_segment_index_cache_key = None
        self._line_segment_index_cache: dict[int, dict] = {}
        self._editable_segments_cache_key = None
        self._editable_segments_cache: list[tuple[int, dict]] = []
        self._editable_segment_pos_cache_key = None
        self._editable_segment_pos_cache: dict[int, int] = {}
        self._speaker_hit_rect_cache_key = None
        self._speaker_hit_rect_cache: dict[tuple, QRect] = {}
        self._speaker_hit_settings_cache_key = None
        self._speaker_hit_settings_cache: dict = {}
        self._drag_snap_base_cache_key = None
        self._drag_snap_base_candidates: list[dict] = []
        self._diamond_pairs_cache_key = None
        self._diamond_pairs_cache: dict[str, object] = {}
        self._scan_boundary_hit_cache = None
        self._voice_activity_segments_external = False
        self._gap_segments_signature = None

    # ---------------------------------------------------------
    # State / Utility
    # ---------------------------------------------------------
    def set_zoom(self, new_pps):
        self.pps = max(5.0, min(500.0, new_pps))
        if getattr(self, "_edit_active", False) and hasattr(self, "_sync_inline_editor_geometry"):
            self._sync_inline_editor_geometry()
        self._update_viewport_region()

    def _pixels_per_frame(self) -> float:
        return max(0.001, float(getattr(self, "pps", 1.0) or 1.0)) / max(1.0, float(self._get_fps() or 30.0))

    def _frame_from_sec(self, sec) -> int:
        return sec_to_nearest_frame(sec, self._get_fps())

    def _sec_from_frame(self, frame: int) -> float:
        return frame_to_sec(frame, self._get_fps())

    def _frame_from_x(self, x) -> int:
        return max(0, int(round(float(x or 0.0) / max(0.001, self._pixels_per_frame()))))

    def _sec_from_x(self, x) -> float:
        return self._sec_from_frame(self._frame_from_x(x))

    def _frame_delta_from_pixels(self, delta_x) -> int:
        return int(round(float(delta_x or 0.0) / max(0.001, self._pixels_per_frame())))

    def _sec_delta_from_pixels(self, delta_x) -> float:
        return float(self._frame_delta_from_pixels(delta_x)) / max(1.0, float(self._get_fps() or 30.0))

    def _frame_x(self, frame: int) -> int:
        return int(round(max(0, int(frame or 0)) * self._pixels_per_frame()))

    def _frame_step_sec(self) -> float:
        return 1.0 / max(1.0, float(self._get_fps() or 30.0))

    def _normalize_canvas_sec(self, sec) -> float:
        try:
            value = float(sec or 0.0)
        except Exception:
            value = 0.0
        return max(0.0, self._snap_to_frame(value))

    def _normalize_canvas_row(self, row: dict, *, preserve_positive_span: bool = True) -> dict:
        item = dict(row or {})
        try:
            raw_start = float(item.get("start", 0.0) or 0.0)
        except Exception:
            raw_start = 0.0
        try:
            raw_end = float(item.get("end", raw_start) or raw_start)
        except Exception:
            raw_end = raw_start
        start = self._normalize_canvas_sec(raw_start)
        end = self._normalize_canvas_sec(raw_end)
        if end < start:
            start, end = end, start
        if preserve_positive_span and raw_end > raw_start and end <= start:
            end = self._normalize_canvas_sec(start + self._frame_step_sec())
        item["start"] = start
        item["end"] = max(start, end)
        return item

    def _normalize_explicit_gap_rows(self, gaps) -> list[dict]:
        normalized: list[dict] = []
        for gap in list(gaps or []):
            if not isinstance(gap, dict):
                continue
            item = self._normalize_canvas_row(gap, preserve_positive_span=False)
            if float(item.get("end", item.get("start", 0.0)) or 0.0) <= float(item.get("start", 0.0) or 0.0):
                continue
            item["_explicit_gap"] = True
            normalized.append(item)
        return normalized

    def _rebuild_gap_segments_from_canvas_state(self, *, source_gaps=None) -> None:
        old_active = {
            (
                self._normalize_canvas_sec(g.get("start", 0.0)),
                self._normalize_canvas_sec(g.get("end", g.get("start", 0.0))),
            )
            for g in list(getattr(self, "gap_segments", []) or [])
            if isinstance(g, dict) and g.get("active")
        }
        explicit_rows = self._normalize_explicit_gap_rows(
            source_gaps
            if source_gaps is not None
            else [g for g in list(getattr(self, "gap_segments", []) or []) if bool(g.get("_explicit_gap"))]
        )
        auto_gaps = _build_gaps(self.segments, self.total_duration, self._get_fps()) if bool(getattr(self, "auto_generate_gap_segments", True)) else []
        if explicit_rows and auto_gaps:
            new_gaps = self._preserve_explicit_gaps(auto_gaps, explicit_rows)
        elif explicit_rows:
            new_gaps = [dict(g) for g in explicit_rows]
        else:
            new_gaps = auto_gaps
        for gap in new_gaps:
            key = (
                self._normalize_canvas_sec(gap.get("start", 0.0)),
                self._normalize_canvas_sec(gap.get("end", gap.get("start", 0.0))),
            )
            if key in old_active:
                gap["active"] = True
        self.gap_segments = new_gaps

    def set_frame_rate(self, fps: float):
        normalized = normalize_fps(fps)
        if abs(float(getattr(self, "frame_rate", 0.0) or 0.0) - normalized) < 0.0001:
            return
        self.frame_rate = normalized
        self.segments = [
            self._normalize_canvas_row(seg)
            for seg in list(getattr(self, "segments", []) or [])
            if isinstance(seg, dict)
        ]
        self._rebuild_gap_segments_from_canvas_state()
        if getattr(self, "active_seg_start", None) is not None:
            self.active_seg_start = self._normalize_canvas_sec(self.active_seg_start)
            self._sync_active_segment_key(self.active_seg_start)
        if getattr(self, "playhead_sec", None) is not None:
            self.playhead_sec = self._normalize_canvas_sec(self.playhead_sec)
        if getattr(self, "llm_review_segment", None):
            self.llm_review_segment = self._normalize_canvas_row(self.llm_review_segment)
        self.user_alignment_guides = self._normalize_user_alignment_guides(getattr(self, "user_alignment_guides", []))
        if getattr(self, "_edit_active", False) and hasattr(self, "_sync_inline_editor_geometry"):
            self._sync_inline_editor_geometry()
        self._invalidate_render_cache()

    def _normalize_user_alignment_guides(self, times) -> list[float]:
        normalized: list[float] = []
        total = max(0.0, float(getattr(self, "total_duration", 0.0) or 0.0))
        for item in list(times or []):
            try:
                sec = self._snap_to_frame(float(item or 0.0))
            except Exception:
                continue
            if sec < 0.0:
                continue
            if total > 0.0 and sec > total + 0.001:
                continue
            if any(abs(sec - prev) < 0.001 for prev in normalized):
                continue
            normalized.append(sec)
        normalized.sort()
        if len(normalized) > 96:
            normalized = normalized[-96:]
        return normalized

    def set_user_alignment_guides(self, times) -> bool:
        normalized = self._normalize_user_alignment_guides(times)
        current = self._normalize_user_alignment_guides(getattr(self, "user_alignment_guides", []))
        if len(normalized) == len(current) and all(abs(a - b) < 0.001 for a, b in zip(normalized, current)):
            return False
        self.user_alignment_guides = normalized
        self._drag_snap_base_cache_key = None
        self._drag_snap_base_candidates = []
        self._render_epoch = int(getattr(self, "_render_epoch", 0) or 0) + 1
        self.update()
        self._notify_scenegraph_layer()
        return True

    def add_user_alignment_guides(self, times) -> bool:
        return self.set_user_alignment_guides(times)

    def _invalidate_marker_caches(self):
        self._analysis_markers_cache_key = None
        self._analysis_markers_cache = []
        self._visible_analysis_markers_cache_key = None
        self._visible_analysis_markers_cache = []
        self._visible_voice_activity_cache_key = None
        self._visible_voice_activity_cache = []
        self._roughcut_major_cache_key = None
        self._roughcut_major_cache = []

    def _invalidate_render_cache(self):
        self._render_epoch = int(getattr(self, "_render_epoch", 0) or 0) + 1
        self._paint_index_cache = {}
        self._paint_last_visible_counts = {}
        self._segment_store = None
        self._segment_store_geometry_signature = None
        self._segment_visual_style_cache = {}
        self._line_segment_index_cache_key = None
        self._line_segment_index_cache = {}
        self._editable_segments_cache_key = None
        self._editable_segments_cache = []
        self._editable_segment_pos_cache_key = None
        self._editable_segment_pos_cache = {}
        self._speaker_hit_rect_cache_key = None
        self._speaker_hit_rect_cache = {}
        self._drag_snap_base_cache_key = None
        self._drag_snap_base_candidates = []
        self._diamond_pairs_cache_key = None
        self._diamond_pairs_cache = {}
        self._scan_boundary_hit_cache = None
        self._visible_analysis_markers_cache_key = None
        self._visible_analysis_markers_cache = []
        self._visible_voice_activity_cache_key = None
        self._visible_voice_activity_cache = []
        self._visible_segment_lanes_cache_key = None
        self._visible_segment_lanes_cache = {}

    def visible_segments_for_time_window(
        self,
        start_sec: float,
        end_sec: float,
        *,
        pad_sec: float = 0.35,
    ) -> list[dict]:
        return self._visible_items_for_paint(
            getattr(self, "segments", []),
            "segments",
            start_sec,
            end_sec,
            pad_sec=pad_sec,
        )

    def visible_segment_lanes_cached(self, visible_segments) -> dict[str, object]:
        from ui.timeline.timeline_segment_style import build_stt_selection_index, final_stt_selection_source, stt_preview_source

        rows = visible_segments if isinstance(visible_segments, list) else list(visible_segments or [])
        key = (
            int(getattr(self, "_render_epoch", 0) or 0),
            id(rows),
            len(rows),
        )
        if key == getattr(self, "_visible_segment_lanes_cache_key", None):
            cached = getattr(self, "_visible_segment_lanes_cache", None)
            if isinstance(cached, dict) and cached:
                return cached

        stt_preview_segments: list[dict] = []
        final_segments: list[dict] = []
        selected_final_segments: list[dict] = []
        stt1_preview_segments: list[dict] = []
        stt2_preview_segments: list[dict] = []
        for seg in rows:
            if not isinstance(seg, dict):
                continue
            if bool(seg.get("stt_pending") or seg.get("_live_stt_preview")):
                stt_preview_segments.append(seg)
                if stt_preview_source(seg) == "STT2":
                    stt2_preview_segments.append(seg)
                else:
                    stt1_preview_segments.append(seg)
                continue
            final_segments.append(seg)
            if final_stt_selection_source(seg):
                selected_final_segments.append(seg)
        data = {
            "visible_segments": rows,
            "stt_preview_segments": stt_preview_segments,
            "final_segments": final_segments,
            "selected_final_segments": selected_final_segments,
            "selected_final_index": build_stt_selection_index(selected_final_segments),
            "stt1_preview_segments": stt1_preview_segments,
            "stt2_preview_segments": stt2_preview_segments,
        }
        self._visible_segment_lanes_cache_key = key
        self._visible_segment_lanes_cache = data
        return data

    def begin_mic_visualization(self, line_num: int | None = None):
        self._is_listening = True
        self._listening_line = None if line_num is None else int(line_num)
        self._mic_waveform_samples = []
        self.update()

    def update_mic_visualization(self, samples):
        self._mic_waveform_samples = list(samples or [])
        self.update()

    def end_mic_visualization(self):
        self._is_listening = False
        self._listening_line = None
        self._mic_waveform_samples = []
        self.update()

    def _paint_time_window(self, rect: QRect | None = None, *, pad_px: int = 96) -> tuple[float, float]:
        rect = rect or self.rect()
        left = max(0, int(rect.left()) - int(pad_px))
        right = max(left + 1, int(rect.right()) + int(pad_px) + 1)
        left_frame = self._frame_from_x(left)
        right_frame = max(left_frame + 1, self._frame_from_x(right))
        return self._sec_from_frame(left_frame), self._sec_from_frame(right_frame)

    def _viewport_paint_clip(self, rect: QRect | None = None, *, pad_px: int = 128) -> QRect:
        """Clamp resize/full-widget repaints to the scroll viewport.

        Zoom and fit-to-view resize the virtual timeline canvas. Qt can then
        send a very wide paint rect even though only the scroll viewport is
        visible, so capping the clip here prevents off-screen segment work.
        """
        paint_rect = QRect(rect) if rect is not None else QRect(self.rect())
        scroll_area = self.parent()
        while scroll_area is not None and not isinstance(scroll_area, QScrollArea):
            scroll_area = scroll_area.parent()
        if scroll_area is None:
            return paint_rect
        try:
            viewport = scroll_area.viewport()
            scroll_x = int(scroll_area.horizontalScrollBar().value())
            viewport_w = max(1, int(viewport.width()))
            viewport_h = max(1, int(viewport.height()))
        except RuntimeError:
            return paint_rect
        except Exception:
            return paint_rect
        visible = QRect(
            max(0, scroll_x - int(pad_px)),
            0,
            viewport_w + int(pad_px) * 2,
            max(int(self.height()), viewport_h),
        )
        return paint_rect.intersected(visible)

    def _update_viewport_region(self, *, pad_px: int = 160) -> None:
        if getattr(self, "_edit_active", False) and hasattr(self, "_sync_inline_editor_geometry"):
            self._sync_inline_editor_geometry()
        try:
            rect = self._viewport_paint_clip(QRect(self.rect()), pad_px=pad_px)
            if rect.isValid() and not rect.isEmpty():
                self.update(rect)
                return
        except Exception:
            pass
        self.update()

    @staticmethod
    def _paint_item_bounds(item: dict) -> tuple[float, float]:
        if isinstance(item, dict):
            try:
                start = float(item.get("start", item.get("timeline_sec", item.get("time", 0.0))) or 0.0)
            except Exception:
                start = 0.0
            try:
                end = float(item.get("end", item.get("timeline_end", start)) or start)
            except Exception:
                end = start
        else:
            try:
                start = float(item or 0.0)
            except Exception:
                start = 0.0
            end = start
        if end < start:
            start, end = end, start
        return start, end

    def _linear_visible_items_for_paint(self, items, start_sec: float, end_sec: float) -> list:
        visible = []
        for item in items or []:
            start, end = self._paint_item_bounds(item)
            if end >= start_sec and start <= end_sec:
                visible.append(item)
        return visible

    def _drag_forced_visible_segments(self, start_sec: float, end_sec: float) -> list[dict]:
        forced: list[dict] = []
        for item in (
            getattr(self, "_drag_seg", None),
            getattr(self, "_drag_adj_l", None),
            getattr(self, "_drag_adj_r", None),
        ):
            if isinstance(item, dict):
                forced.append(item)

        pair = getattr(self, "_drag_diamond_pair", None)
        if pair is not None:
            for idx in pair:
                try:
                    item = self.segments[int(idx)]
                except Exception:
                    item = None
                if isinstance(item, dict):
                    forced.append(item)

        visible: list[dict] = []
        seen: set[int] = set()
        for item in forced:
            marker = id(item)
            if marker in seen:
                continue
            seen.add(marker)
            item_start, item_end = self._paint_item_bounds(item)
            if item_end >= start_sec and item_start <= end_sec:
                visible.append(item)
        return visible

    def _merge_forced_visible_segments(self, visible: list, start_sec: float, end_sec: float) -> list:
        if not (
            getattr(self, "_drag_seg", None) is not None
            or getattr(self, "_drag_diamond_pair", None) is not None
        ):
            return visible
        merged = list(visible or [])
        seen = {id(item) for item in merged}
        for item in self._drag_forced_visible_segments(start_sec, end_sec):
            if id(item) not in seen:
                merged.append(item)
                seen.add(id(item))
        return merged

    def _visible_items_for_paint(
        self,
        items,
        cache_name: str,
        start_sec: float,
        end_sec: float,
        *,
        pad_sec: float = 0.0,
    ) -> list:
        rows = items if isinstance(items, list) else list(items or [])
        start_sec = max(0.0, float(start_sec or 0.0) - float(pad_sec or 0.0))
        end_sec = max(start_sec, float(end_sec or start_sec) + float(pad_sec or 0.0))
        if not rows:
            self._paint_last_visible_counts[str(cache_name)] = 0
            return []
        if len(rows) < 64:
            visible = self._linear_visible_items_for_paint(rows, start_sec, end_sec)
            if str(cache_name or "") == "segments":
                visible = self._merge_forced_visible_segments(visible, start_sec, end_sec)
            self._paint_last_visible_counts[str(cache_name)] = len(visible)
            return visible

        cache_name = str(cache_name or "items")
        if cache_name == "segments" and rows is self.segments:
            store = getattr(self, "_segment_store", None)
            if store is None or len(store.rows) != len(self.segments):
                store = TimelineSegmentStore(self.segments)
                self._segment_store = store
            visible = store.visible(start_sec, end_sec)
            visible = self._merge_forced_visible_segments(visible, start_sec, end_sec)
            self._paint_last_visible_counts[cache_name] = len(visible)
            return visible
        sig = (id(items), len(rows), int(getattr(self, "_render_epoch", 0) or 0))
        paint_index_cache = getattr(self, "_paint_index_cache", {})
        cache = paint_index_cache.get(cache_name) or {}
        if cache.get("sig") != sig:
            by_start = []
            max_span = 0.0
            for idx, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                start, end = self._paint_item_bounds(row)
                max_span = max(max_span, max(0.0, end - start))
                by_start.append((start, end, idx, row))
            by_start.sort(key=lambda item: (item[0], item[1], item[2]))
            cache = {
                "sig": sig,
                "by_start": by_start,
                "starts": [item[0] for item in by_start],
                "max_span": max_span,
            }
            self._paint_index_cache[cache_name] = cache

        starts = cache.get("starts") or []
        by_start = cache.get("by_start") or []
        if not by_start:
            self._paint_last_visible_counts[cache_name] = 0
            return []

        max_span = max(0.0, float(cache.get("max_span", 0.0) or 0.0))
        start_index = bisect_left(starts, max(0.0, start_sec - max_span))
        end_index = bisect_right(starts, end_sec)
        candidates = by_start[start_index:end_index]
        visible = [
            row
            for item_start, item_end, _idx, row in candidates
            if item_end >= start_sec and item_start <= end_sec
        ]
        if cache_name == "segments":
            visible = self._merge_forced_visible_segments(visible, start_sec, end_sec)
        self._paint_last_visible_counts[cache_name] = len(visible)
        return visible

    def _paint_window_signature(self, rows) -> tuple:
        rows = rows or []
        if not rows:
            return (0, None, None, None, None)
        first = rows[0] if isinstance(rows[0], dict) else {}
        last = rows[-1] if isinstance(rows[-1], dict) else {}
        first_start, _first_end = self._paint_item_bounds(first)
        _last_start, last_end = self._paint_item_bounds(last)
        return (
            len(rows),
            round(float(first_start or 0.0), 3),
            round(float(last_end or 0.0), 3),
            id(first),
            id(last),
        )

    def visible_voice_activity_segments_cached(
        self,
        start_sec: float,
        end_sec: float,
        visible_segments=None,
        visible_vad_segments=None,
        visible_gap_segments=None,
    ) -> list[dict]:
        """Build subtitle-detection lane data only for the visible paint window."""
        from ui.timeline.timeline_analysis import subtitle_detection_segments_for_editor

        start_sec = max(0.0, float(start_sec or 0.0))
        end_sec = max(start_sec, float(end_sec or start_sec))
        key = (
            int(getattr(self, "_render_epoch", 0) or 0),
            round(start_sec, 2),
            round(end_sec, 2),
            self._paint_window_signature(visible_segments),
            self._paint_window_signature(visible_vad_segments),
            self._paint_window_signature(visible_gap_segments),
            round(float(getattr(self, "total_duration", 0.0) or 0.0), 3),
        )
        if self._visible_voice_activity_cache_key != key:
            markers = subtitle_detection_segments_for_editor(
                list(visible_segments or []),
                list(visible_vad_segments or []),
                list(visible_gap_segments or []),
                float(getattr(self, "total_duration", 0.0) or 0.0),
            )
            self._visible_voice_activity_cache = self._linear_visible_items_for_paint(
                markers,
                start_sec,
                end_sec,
            )
            self._visible_voice_activity_cache_key = key
        return list(self._visible_voice_activity_cache)

    def _items_near_x_for_hit(self, items, cache_name: str, x: int | float, *, pad_px: int = 24) -> list:
        center_sec = self._sec_from_x(x)
        pad_frames = max(1, int(math.ceil(float(pad_px or 0) / max(0.001, self._pixels_per_frame()))))
        pad_sec = max(self._frame_step_sec(), float(pad_frames) / max(1.0, float(self._get_fps() or 30.0)))
        return self._visible_items_for_paint(items, cache_name, center_sec, center_sec, pad_sec=pad_sec)

    def _segments_near_x_for_hit(self, x: int | float, *, pad_px: int = 24) -> list[dict]:
        return self._items_near_x_for_hit(getattr(self, "segments", []) or [], "segments", x, pad_px=pad_px)

    def _gaps_near_x_for_hit(self, x: int | float, *, pad_px: int = 24) -> list[dict]:
        return self._items_near_x_for_hit(getattr(self, "gap_segments", []) or [], "gaps", x, pad_px=pad_px)

    def _multiclip_boxes_near_x_for_hit(self, x: int | float, *, pad_px: int = 24) -> list[dict]:
        return self._items_near_x_for_hit(getattr(self, "_multiclip_boxes", []) or [], "multiclip_boxes", x, pad_px=pad_px)

    def _segment_index_cache_key(self) -> tuple:
        return (
            int(getattr(self, "_render_epoch", 0) or 0),
            id(getattr(self, "segments", None)),
            len(getattr(self, "segments", []) or []),
        )

    def _segment_for_line(self, line_num: int):
        key = self._segment_index_cache_key()
        if self._line_segment_index_cache_key != key:
            index: dict[int, dict] = {}
            for seg in list(getattr(self, "segments", []) or []):
                if not isinstance(seg, dict):
                    continue
                try:
                    line = int(seg.get("line", -999999))
                except Exception:
                    continue
                index.setdefault(line, seg)
            self._line_segment_index_cache_key = key
            self._line_segment_index_cache = index
        try:
            return self._line_segment_index_cache.get(int(line_num))
        except Exception:
            return None

    def _active_segment_candidates(self) -> list[dict]:
        active_line = getattr(self, "active_seg_line", None)
        if active_line is not None:
            seg = self._segment_for_line(int(active_line))
            return [seg] if isinstance(seg, dict) else []

        active = getattr(self, "active_seg_start", None)
        if active is None:
            return []
        try:
            center = float(active)
        except Exception:
            return []
        return self._visible_items_for_paint(self.segments, "segments", center, center, pad_sec=0.55)

    def _refresh_voice_activity_segments(self):
        try:
            from ui.timeline.timeline_analysis import voice_activity_segments_for_editor

            self.voice_activity_segments = voice_activity_segments_for_editor(
                list(getattr(self, "segments", []) or []),
                list(getattr(self, "vad_segments", []) or []),
                list(getattr(self, "gap_segments", []) or []),
                float(getattr(self, "total_duration", 0.0) or 0.0),
            )
            self._voice_activity_segments_external = False
        except Exception:
            self.voice_activity_segments = []
            self._voice_activity_segments_external = False

    def analysis_markers_cached(self) -> list[dict]:
        from ui.timeline.timeline_analysis import analysis_markers_for_widget

        key = (
            int(getattr(self, "_render_epoch", 0) or 0),
            id(self.segments),
            id(self.vad_segments),
            id(self.gap_segments),
            len(self.segments),
            len(self.vad_segments),
            len(self.gap_segments),
            round(float(self.total_duration or 0.0), 3),
        )
        if self._analysis_markers_cache_key != key:
            self._analysis_markers_cache = analysis_markers_for_widget(
                self,
                list(getattr(self, "segments", []) or []),
                list(getattr(self, "vad_segments", []) or []),
                list(getattr(self, "gap_segments", []) or []),
                float(getattr(self, "total_duration", 0.0) or 0.0),
            )
            self._analysis_markers_cache_key = key
        return list(self._analysis_markers_cache)

    def analysis_markers_visible_cached(
        self,
        start_sec: float,
        end_sec: float,
        visible_segments=None,
        visible_vad_segments=None,
        visible_gap_segments=None,
    ) -> list[dict]:
        """Return analysis markers for the visible viewport instead of the full project."""
        from ui.timeline.timeline_analysis import analysis_markers_for_widget

        start_sec = max(0.0, float(start_sec or 0.0))
        end_sec = max(start_sec, float(end_sec or start_sec))
        key = (
            int(getattr(self, "_render_epoch", 0) or 0),
            round(start_sec, 2),
            round(end_sec, 2),
            self._paint_window_signature(visible_segments),
            self._paint_window_signature(visible_vad_segments),
            self._paint_window_signature(visible_gap_segments),
            round(float(getattr(self, "total_duration", 0.0) or 0.0), 3),
        )
        if self._visible_analysis_markers_cache_key != key:
            markers = analysis_markers_for_widget(
                self,
                list(visible_segments or []),
                list(visible_vad_segments or []),
                list(visible_gap_segments or []),
                float(getattr(self, "total_duration", 0.0) or 0.0),
            )
            self._visible_analysis_markers_cache = self._linear_visible_items_for_paint(
                markers,
                start_sec,
                end_sec,
            )
            self._visible_analysis_markers_cache_key = key
        return list(self._visible_analysis_markers_cache)

    def generation_silence_markers_cached(self) -> list[dict]:
        from ui.timeline.timeline_analysis import subtitle_generation_silence_segments_for_editor

        key = (
            "generation_silence",
            int(getattr(self, "_render_epoch", 0) or 0),
            id(self.gap_segments),
            len(self.gap_segments),
            round(float(self.total_duration or 0.0), 3),
        )
        cache_key = getattr(self, "_generation_silence_cache_key", None)
        if cache_key != key:
            self._generation_silence_markers_cache = subtitle_generation_silence_segments_for_editor(
                list(getattr(self, "gap_segments", []) or []),
                float(getattr(self, "total_duration", 0.0) or 0.0),
            )
            self._generation_silence_cache_key = key
        return list(getattr(self, "_generation_silence_markers_cache", []))

    def roughcut_major_markers_cached(self) -> list[dict]:
        from ui.timeline.timeline_analysis import find_roughcut_result, roughcut_major_markers

        result = find_roughcut_result(self)
        result_segments = tuple(getattr(result, "segments", ()) or ()) if result is not None else ()
        key = (
            id(result),
            tuple(
                (
                    str(getattr(seg, "id", "") or getattr(seg, "segment_id", "") or ""),
                    str(getattr(seg, "major_id", "") or ""),
                    round(float(getattr(seg, "start", 0.0) or 0.0), 3),
                    round(float(getattr(seg, "end", 0.0) or 0.0), 3),
                    str(getattr(seg, "title", "") or ""),
                    str(getattr(seg, "status", "") or ""),
                )
                for seg in result_segments
            ),
        )
        if self._roughcut_major_cache_key != key:
            self._roughcut_major_cache = roughcut_major_markers(result) if result is not None else []
            self._roughcut_major_cache_key = key
        return list(self._roughcut_major_cache)

    def update_segments(self, segs, active_sec, total_dur):
        rows = list(segs or [])
        source_gaps = []
        segments = []
        geometry_checksum = 0
        source_gap_checksum = 0
        content_end_ms = 0
        for s in rows:
            if not isinstance(s, dict):
                continue
            if s.get("is_gap"):
                source_gap = self._normalize_canvas_row(s, preserve_positive_span=False)
                start_ms = int(round(float(source_gap.get("start", 0.0) or 0.0) * 1000.0))
                end_ms = int(round(float(source_gap.get("end", source_gap.get("start", 0.0)) or 0.0) * 1000.0))
                if end_ms > start_ms:
                    source_gap["_explicit_gap"] = True
                    source_gaps.append(source_gap)
                    source_gap_checksum = (
                        (source_gap_checksum * 1000003)
                        ^ (start_ms * 131)
                        ^ (end_ms * 17)
                    ) & 0xFFFFFFFF
                continue
            segment = self._normalize_canvas_row(s)
            start_ms = int(round(float(segment.get("start", 0.0) or 0.0) * 1000.0))
            end_ms = int(round(float(segment.get("end", segment.get("start", 0.0)) or 0.0) * 1000.0))
            segments.append(segment)
            content_end_ms = max(content_end_ms, end_ms)
            geometry_checksum = ((geometry_checksum * 1000003) ^ (start_ms * 31) ^ end_ms) & 0xFFFFFFFF
        previous_geometry_signature = getattr(self, "_segments_geometry_signature", None)
        self.segments = segments
        self.total_duration = total_dur or (rows[-1]["end"] if rows else 0.0)
        self._segments_content_duration = max(
            float(self.total_duration or 0.0),
            float(content_end_ms) / 1000.0,
        )

        segments_geometry_signature = (
            len(self.segments),
            int(round(float(self.total_duration or 0.0) * 1000.0)),
            geometry_checksum,
        )
        gap_signature = (
            len(self.segments),
            int(round(float(self.total_duration or 0.0) * 1000.0)),
            len(source_gaps),
            bool(getattr(self, "auto_generate_gap_segments", True)),
            geometry_checksum,
            source_gap_checksum,
        )
        self._segments_geometry_signature = segments_geometry_signature
        gaps_changed = bool(source_gaps) or gap_signature != getattr(self, "_gap_segments_signature", None)
        if gaps_changed:
            self._rebuild_gap_segments_from_canvas_state(source_gaps=source_gaps)
            for gap in self.gap_segments:
                for source in source_gaps:
                    try:
                        same_start = abs(float(source.get("start", 0.0) or 0.0) - float(gap.get("start", 0.0) or 0.0)) < 0.05
                        same_end = abs(float(source.get("end", 0.0) or 0.0) - float(gap.get("end", 0.0) or 0.0)) < 0.05
                    except Exception:
                        same_start = same_end = False
                    if not (same_start and same_end):
                        continue
                    for key in ("quality", "quality_history", "quality_candidates", "linked_silence_for_line"):
                        if key in source:
                            gap[key] = source[key]
                    break
            self._gap_segments_signature = gap_signature
        if not bool(getattr(self, "_voice_activity_segments_external", False)):
            self.voice_activity_segments = []
        if gaps_changed:
            self._invalidate_marker_caches()
            self._invalidate_render_cache()
        else:
            self._line_segment_index_cache_key = None
            self._line_segment_index_cache = {}
            self._editable_segments_cache_key = None
            self._editable_segments_cache = []
            self._editable_segment_pos_cache_key = None
            self._editable_segment_pos_cache = {}
            self._speaker_hit_rect_cache_key = None
            self._speaker_hit_rect_cache = {}
            self._drag_snap_base_cache_key = None
            self._drag_snap_base_candidates = []
            if len(getattr(self, "_segment_visual_style_cache", {}) or {}) > 4096:
                self._segment_visual_style_cache = {}

        if len(self.segments) >= 64:
            store = getattr(self, "_segment_store", None)
            store_sig = getattr(self, "_segment_store_geometry_signature", None)
            if (
                store is not None
                and store_sig == segments_geometry_signature
                and previous_geometry_signature == segments_geometry_signature
                and len(getattr(store, "rows", []) or []) == len(self.segments)
            ):
                store.set_rows(self.segments)
            else:
                store = TimelineSegmentStore(self.segments)
                self._segment_store = store
            self._segment_store_geometry_signature = segments_geometry_signature
        else:
            self._segment_store = None
            self._segment_store_geometry_signature = None

        if active_sec is not None:
            self.active_seg_start = self._normalize_canvas_sec(active_sec)
            self._sync_active_segment_key(self.active_seg_start)

        if getattr(self, "_edit_active", False) and hasattr(self, "_sync_inline_editor_geometry"):
            self._sync_inline_editor_geometry()
        self._update_viewport_region()

    def set_llm_review_segment(self, payload: dict | None) -> None:
        data = dict(payload or {})
        if not data.get("active"):
            self.llm_review_segment = None
            self.update()
            return
        try:
            start = max(0.0, float(data.get("start", 0.0) or 0.0))
            end = max(start, float(data.get("end", start) or start))
        except Exception:
            self.llm_review_segment = None
            self.update()
            return
        if end <= start:
            end = start + self._frame_step_sec()
        data["start"] = start
        data["end"] = end
        self.llm_review_segment = self._normalize_canvas_row(data)
        self.update()

    def _preserve_explicit_gaps(self, generated_gaps: list[dict], source_gaps: list[dict]) -> list[dict]:
        preserved: list[dict] = []
        explicit = sorted(source_gaps or [], key=lambda gap: (float(gap.get("start", 0.0) or 0.0), float(gap.get("end", 0.0) or 0.0)))
        min_gap = 0.05

        def _gap_copy(base: dict, start: float, end: float) -> dict:
            item = dict(base)
            item["start"] = start
            item["end"] = end
            item["text"] = ""
            item["is_gap"] = True
            item.setdefault("active", False)
            return item

        for generated in generated_gaps or []:
            gs = float(generated.get("start", 0.0) or 0.0)
            ge = float(generated.get("end", gs) or gs)
            if ge <= gs + min_gap:
                continue
            cursor = gs
            matched = False

            for source in explicit:
                ss = float(source.get("start", 0.0) or 0.0)
                se = float(source.get("end", ss) or ss)
                if se <= gs + min_gap or ss >= ge - min_gap:
                    continue
                matched = True
                if ss > cursor + min_gap:
                    preserved.append(_gap_copy(generated, cursor, min(ss, ge)))
                start = max(gs, ss)
                end = min(ge, se)
                if end > start + min_gap:
                    preserved.append(_gap_copy(source, start, end))
                cursor = max(cursor, end)

            if not matched:
                preserved.append(dict(generated))
            elif cursor < ge - min_gap:
                preserved.append(_gap_copy(generated, cursor, ge))

        return preserved

    def _sync_active_segment_key(self, sec=None, seg=None):
        if seg is None and sec is not None:
            try:
                target = float(sec)
                candidates = self._visible_items_for_paint(self.segments, "segments", target, target, pad_sec=0.55)
                seg = next(
                    (
                        item for item in candidates
                        if abs(float(item.get("start", 0.0) or 0.0) - target) < 0.001
                    ),
                    None,
                )
                if seg is None:
                    seg = next(
                        (
                            item for item in candidates
                            if float(item.get("start", 0.0) or 0.0) <= target < float(item.get("end", 0.0) or 0.0)
                        ),
                        None,
                    )
            except Exception:
                seg = None
        if seg is not None:
            try:
                self.active_seg_line = int(seg.get("line", -1))
            except Exception:
                self.active_seg_line = None
        elif sec is None:
            self.active_seg_line = None

    def _is_active_segment(self, seg) -> bool:
        if hasattr(self, "_timeline_playback_active") and self._timeline_playback_active():
            try:
                start = float(seg.get("start", 0.0) or 0.0)
                end = float(seg.get("end", start) or start)
                playhead = float(getattr(self, "playhead_sec", 0.0) or 0.0)
                fps = max(1.0, float(self._get_fps() or 30.0))
                edge_tol = max(0.001, min(0.05, 2.0 / fps))
                return start - edge_tol <= playhead < end + edge_tol
            except Exception:
                return False
        active_line = getattr(self, "active_seg_line", None)
        if active_line is not None:
            try:
                return int(seg.get("line", -999999)) == int(active_line)
            except Exception:
                return False
        active = getattr(self, "active_seg_start", None)
        if active is None:
            return False
        try:
            return abs(float(seg.get("start", 0.0) or 0.0) - float(active)) < 0.001
        except Exception:
            return False

    def set_vad_segments(self, vad_segs):
        self.vad_segments = vad_segs
        self._speech_mask = None      # 마스크 재계산 트리거
        self._waveform_line_cache_key = None
        self._waveform_line_cache = None
        if not bool(getattr(self, "_voice_activity_segments_external", False)):
            self.voice_activity_segments = []
        self._invalidate_marker_caches()
        self._invalidate_render_cache()
        self.update()

    def set_voice_activity_segments(self, segments: list[dict]):
        self.voice_activity_segments = list(segments or [])
        self._voice_activity_segments_external = True
        self._invalidate_render_cache()
        self.update()

    def set_active(self, sec):
        old_rect = self._active_segment_repaint_rect()
        self.active_seg_start = self._normalize_canvas_sec(sec)
        self._sync_active_segment_key(self.active_seg_start)
        if getattr(self, "_edit_active", False) and hasattr(self, "_sync_inline_editor_geometry"):
            self._sync_inline_editor_geometry()
        dirty = old_rect.united(self._active_segment_repaint_rect())
        self._update_dirty_rect(dirty)

    def set_playhead(self, sec):
        sec = self._snap_to_frame(sec)
        px = self._x(sec)
        if self.playhead_sec == sec or self._last_playhead_px == px:
            return
        old_px = self._last_playhead_px
        self.playhead_sec = sec
        self._last_playhead_px = px
        if getattr(self, "_external_playhead_overlay", False):
            return
        if old_px is None:
            self.update(QRect(max(0, px - 12), 0, 24, CANVAS_H))
        else:
            left = max(0, min(old_px, px) - 12)
            right = min(self.width(), max(old_px, px) + 13)
            self.update(QRect(left, 0, max(1, right - left), CANVAS_H))

    def set_waveform(self, wf):
        self._waveform = wf
        self._speech_mask = None
        self._waveform_line_cache_key = None
        self._waveform_line_cache = None
        self._invalidate_render_cache()
        self.update()

    def _x(self, sec):
        return self._frame_x(self._frame_from_sec(sec))

    def total_width(self):
        total_frames = frame_count(getattr(self, "total_duration", 0.0), self._get_fps())
        return max(self.width(), self._frame_x(total_frames) + 96)

    def _icon_rect(self, x1, x2):
        return QRect(x1 + (x2 - x1) // 2 - (ICON_SZ // 2), SEG_TOP + 22, ICON_SZ, ICON_SZ)

    def _plus_rect(self, x1, x2):
        return QRect(x1 + (x2 - x1) // 2 - (ICON_SZ // 2), SEG_TOP + 22, ICON_SZ, ICON_SZ)

    def _seg_at(self, x):
        candidates = self._segments_near_x_for_hit(x, pad_px=12) if hasattr(self, "_segments_near_x_for_hit") else self.segments
        for seg in candidates:
            if bool(seg.get("stt_pending") or seg.get("_live_stt_preview") or seg.get("_live_subtitle_preview")):
                continue
            if self._x(seg["start"]) <= x <= self._x(seg["end"]):
                return seg
        return None

    def _segment_repaint_rect(self, seg, *, margin: int = 34, full_height: bool = False) -> QRect:
        if not seg:
            return QRect()
        try:
            x1 = self._x(float(seg.get("start", 0.0) or 0.0))
            x2 = self._x(float(seg.get("end", 0.0) or 0.0))
        except Exception:
            return QRect()
        frame_px = int(max(2.0, (1.0 / max(1.0, float(self._get_fps()))) * max(1.0, float(self.pps or 1.0))))
        margin = int(margin) + frame_px
        left = max(0, min(x1, x2) - margin)
        right = min(max(self.width(), self.total_width()), max(x1, x2) + int(margin))
        top = 0 if full_height else max(0, SEG_TOP - 18)
        bottom = CANVAS_H if full_height else CANVAS_H
        return QRect(left, top, max(1, right - left), max(1, bottom - top))

    def _segment_repaint_rect_for_line(self, line_num: int, *, margin: int = 34) -> QRect:
        seg = self._segment_for_line(int(line_num)) if hasattr(self, "_segment_for_line") else next((s for s in self.segments if int(s.get("line", -999999)) == int(line_num)), None)
        return self._segment_repaint_rect(seg, margin=margin)

    def _active_segment_repaint_rect(self) -> QRect:
        if getattr(self, "active_seg_start", None) is None and getattr(self, "active_seg_line", None) is None:
            return QRect()
        dirty = QRect()
        candidates = self._active_segment_candidates() if hasattr(self, "_active_segment_candidates") else self.segments
        for seg in candidates:
            if self._is_active_segment(seg):
                rect = self._segment_repaint_rect(seg, margin=48)
                dirty = rect if dirty.isNull() else dirty.united(rect)
        return dirty

    def _update_dirty_rect(self, rect: QRect):
        if rect.isValid() and not rect.isEmpty():
            self.update(rect.intersected(QRect(0, 0, max(1, self.width()), max(1, self.height()))))
        else:
            self.update()
        self._notify_scenegraph_layer()

    def _notify_scenegraph_layer(self):
        owner = self.parent()
        while owner is not None:
            sync = getattr(owner, "_sync_scenegraph_layer", None)
            if callable(sync):
                sync()
                return
            owner = owner.parent()

    def _get_prev_seg(self, seg):
        key = self._segment_index_cache_key()
        if self._editable_segments_cache_key != key:
            self._editable_segments_sorted()
        pos = self._editable_segment_pos_cache.get(id(seg))
        if pos is None or pos <= 0:
            return None
        try:
            return self._editable_segments_cache[int(pos) - 1][1]
        except Exception:
            return None

    def _get_next_seg(self, seg):
        key = self._segment_index_cache_key()
        if self._editable_segments_cache_key != key:
            self._editable_segments_sorted()
        pos = self._editable_segment_pos_cache.get(id(seg))
        if pos is None:
            return None
        try:
            next_pos = int(pos) + 1
            if next_pos >= len(self._editable_segments_cache):
                return None
            return self._editable_segments_cache[next_pos][1]
        except Exception:
            return None

    def _editable_segments_sorted(self):
        key = self._segment_index_cache_key()
        if self._editable_segments_cache_key != key:
            editable: list[tuple[int, dict]] = []
            for raw_idx, seg in enumerate(self.segments):
                if not isinstance(seg, dict):
                    continue
                if seg.get("is_gap") or bool(seg.get("stt_pending") or seg.get("_live_stt_preview") or seg.get("_live_subtitle_preview")):
                    continue
                editable.append((raw_idx, seg))
            editable.sort(key=lambda item: (float(item[1].get("start", 0.0) or 0.0), float(item[1].get("end", 0.0) or 0.0), int(item[0])))
            self._editable_segments_cache_key = key
            self._editable_segments_cache = editable
            self._editable_segment_pos_cache_key = key
            self._editable_segment_pos_cache = {id(seg): pos for pos, (_idx, seg) in enumerate(editable)}
        return [seg for _idx, seg in list(self._editable_segments_cache or [])]

    def _editable_segments_with_indices_sorted(self):
        key = self._segment_index_cache_key()
        if self._editable_segments_cache_key != key:
            self._editable_segments_sorted()
        return list(self._editable_segments_cache or [])

    def _get_fps(self):
        if float(getattr(self, "frame_rate", 0.0) or 0.0) > 0:
            return float(self.frame_rate)
        widget = self.parent()
        while widget:
            if hasattr(widget, "video_fps"):
                return float(widget.video_fps)
            widget = widget.parent()
        return 30.0

    def _snap_to_frame(self, sec):
        return snap_sec_to_frame(sec, self._get_fps())
