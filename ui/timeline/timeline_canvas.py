# Version: 03.14.31
# Phase: PHASE2
"""
ui/timeline_canvas.py
Timeline canvas
"""
from bisect import bisect_left, bisect_right

import numpy as np
from PyQt6.QtCore import QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QSizePolicy

from core.frame_time import normalize_fps, snap_sec_to_frame

from ui.timeline.timeline_constants import (
    CANVAS_H,
    ICON_SZ,
    SEG_TOP,
    _build_gaps,
)
from ui.timeline.timeline_paint import TimelinePaintMixin
from ui.timeline.timeline_input import TimelineInputMixin
from ui.timeline.timeline_inline_edit import TimelineInlineEditMixin
from ui.gpu_rendering import accelerated_widget_base, configure_lightweight_paint, configure_opengl_widget, gpu_backend_name


TimelineCanvasBase = accelerated_widget_base("timeline")


class TimelineCanvas(TimelineInlineEditMixin, TimelineInputMixin, TimelinePaintMixin, TimelineCanvasBase):
    seg_clicked             = pyqtSignal(int, float)
    seg_right_clicked       = pyqtSignal(float, QPoint)
    stt_candidate_selected  = pyqtSignal(dict)
    seg_double_clicked      = pyqtSignal(int, float)
    seg_time_changed        = pyqtSignal(int, float, float, str)
    seg_to_gap              = pyqtSignal(int)
    gap_activated           = pyqtSignal(float, float)
    gap_to_segs             = pyqtSignal(float, float)
    gap_generate_requested  = pyqtSignal(float, float, float, str)
    scrub_sec               = pyqtSignal(float)
    drag_started            = pyqtSignal()
    drag_finished           = pyqtSignal()
    step_frame              = pyqtSignal(int)
    sig_inline_text_changed = pyqtSignal(int, str)
    sig_editing_mode        = pyqtSignal(bool)
    sig_split_request       = pyqtSignal(int, float, int)
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

        self._snap_lines = []
        self._drag_guide_x: int | None = None
        self._drag_snap_candidate: dict | None = None
        self._is_scrubbing = False
        self._is_panning = False

        self._edit_active   = False
        self._edit_line     = -1
        self._edit_text     = ""
        self._edit_orig     = ""
        self._edit_cursor   = 0
        self._cursor_vis    = True
        self._cursor_timer  = QTimer(self)
        self._cursor_timer.setInterval(500)
        self._cursor_timer.timeout.connect(self._blink_cursor)

        self._speech_mask: np.ndarray | None = None
        self._speech_mask_wf_len: int = 0
        self._analysis_markers_cache_key = None
        self._analysis_markers_cache: list[dict] = []
        self._roughcut_major_cache_key = None
        self._roughcut_major_cache: list[dict] = []
        self._render_epoch = 0
        self._paint_index_cache: dict[str, dict] = {}
        self._paint_last_visible_counts: dict[str, int] = {}
        self._line_segment_index_cache_key = None
        self._line_segment_index_cache: dict[int, dict] = {}
        self._editable_segments_cache_key = None
        self._editable_segments_cache: list[tuple[int, dict]] = []
        self._diamond_pairs_cache_key = None
        self._diamond_pairs_cache: dict[str, object] = {}
        self._scan_boundary_hit_cache = None

    # ---------------------------------------------------------
    # State / Utility
    # ---------------------------------------------------------
    def set_zoom(self, new_pps):
        self.pps = max(5.0, min(500.0, new_pps))
        self.update()

    def set_frame_rate(self, fps: float):
        normalized = normalize_fps(fps)
        if abs(float(getattr(self, "frame_rate", 0.0) or 0.0) - normalized) < 0.0001:
            return
        self.frame_rate = normalized
        self._invalidate_render_cache()

    def _invalidate_marker_caches(self):
        self._analysis_markers_cache_key = None
        self._analysis_markers_cache = []
        self._roughcut_major_cache_key = None
        self._roughcut_major_cache = []

    def _invalidate_render_cache(self):
        self._render_epoch = int(getattr(self, "_render_epoch", 0) or 0) + 1
        self._paint_index_cache = {}
        self._paint_last_visible_counts = {}
        self._line_segment_index_cache_key = None
        self._line_segment_index_cache = {}
        self._editable_segments_cache_key = None
        self._editable_segments_cache = []
        self._diamond_pairs_cache_key = None
        self._diamond_pairs_cache = {}
        self._scan_boundary_hit_cache = None

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
        pps = max(0.001, float(getattr(self, "pps", 1.0) or 1.0))
        left = max(0, int(rect.left()) - int(pad_px))
        right = max(left + 1, int(rect.right()) + int(pad_px) + 1)
        return max(0.0, left / pps), max(0.0, right / pps)

    @staticmethod
    def _paint_item_bounds(item: dict) -> tuple[float, float]:
        try:
            start = float(item.get("start", item.get("timeline_sec", item.get("time", 0.0))) or 0.0)
        except Exception:
            start = 0.0
        try:
            end = float(item.get("end", item.get("timeline_end", start)) or start)
        except Exception:
            end = start
        if end < start:
            start, end = end, start
        return start, end

    def _linear_visible_items_for_paint(self, items, start_sec: float, end_sec: float) -> list:
        visible = []
        for item in list(items or []):
            if not isinstance(item, dict):
                continue
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
        rows = list(items or [])
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
        sig = (id(items), len(rows), int(getattr(self, "_render_epoch", 0) or 0))
        cache = dict(getattr(self, "_paint_index_cache", {}).get(cache_name) or {})
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

        starts = list(cache.get("starts") or [])
        by_start = list(cache.get("by_start") or [])
        if not by_start:
            self._paint_last_visible_counts[cache_name] = 0
            return []

        max_span = max(0.0, float(cache.get("max_span", 0.0) or 0.0))
        start_index = bisect_left(starts, max(0.0, start_sec - max_span))
        end_index = bisect_right(starts, end_sec)
        candidates = by_start[start_index:end_index]
        visible = [
            row
            for _start, _end, _idx, row in candidates
            if self._paint_item_bounds(row)[1] >= start_sec
            and self._paint_item_bounds(row)[0] <= end_sec
        ]
        if cache_name == "segments":
            visible = self._merge_forced_visible_segments(visible, start_sec, end_sec)
        self._paint_last_visible_counts[cache_name] = len(visible)
        return visible

    def _items_near_x_for_hit(self, items, cache_name: str, x: int | float, *, pad_px: int = 24) -> list:
        pps = max(0.001, float(getattr(self, "pps", 1.0) or 1.0))
        center_sec = max(0.0, float(x or 0.0) / pps)
        pad_sec = max(0.02, float(pad_px or 0) / pps)
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
        except Exception:
            self.voice_activity_segments = []

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
        source_gaps = [
            dict(s)
            for s in list(segs or [])
            if s.get("is_gap") and float(s.get("end", s.get("start", 0.0)) or 0.0) > float(s.get("start", 0.0) or 0.0)
        ]
        self.segments = [s for s in segs if not s.get("is_gap")]
        self.total_duration = total_dur or (segs[-1]["end"] if segs else 0.0)

        generated_gaps = _build_gaps(self.segments, self.total_duration)
        if source_gaps:
            new_gaps = self._preserve_explicit_gaps(generated_gaps, source_gaps)
        else:
            new_gaps = generated_gaps
        old_active = {
            (g["start"], g["end"])
            for g in self.gap_segments
            if g.get("active")
        }

        for gap in new_gaps:
            if (gap["start"], gap["end"]) in old_active:
                gap["active"] = True
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

        self.gap_segments = new_gaps
        self._refresh_voice_activity_segments()
        self._invalidate_marker_caches()
        self._invalidate_render_cache()

        if active_sec is not None:
            self.active_seg_start = active_sec
            self._sync_active_segment_key(active_sec)

        self.update()

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
            end = start + max(0.05, 1.0 / max(1.0, float(getattr(self, "frame_rate", 30.0) or 30.0)))
        data["start"] = start
        data["end"] = end
        self.llm_review_segment = data
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
        self._refresh_voice_activity_segments()
        self._invalidate_marker_caches()
        self._invalidate_render_cache()
        self.update()

    def set_voice_activity_segments(self, segments: list[dict]):
        self.voice_activity_segments = list(segments or [])
        self._invalidate_render_cache()
        self.update()

    def set_active(self, sec):
        old_rect = self._active_segment_repaint_rect()
        self.active_seg_start = sec
        self._sync_active_segment_key(sec)
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
        self._invalidate_render_cache()
        self.update()

    def _x(self, sec):
        return int(sec * self.pps)

    def total_width(self):
        return max(self.width(), int(self.total_duration * self.pps) + 96)

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
        segs = self._editable_segments_sorted()
        try:
            idx = segs.index(seg)
            return segs[idx - 1] if idx > 0 else None
        except ValueError:
            return None

    def _get_next_seg(self, seg):
        segs = self._editable_segments_sorted()
        try:
            idx = segs.index(seg)
            return segs[idx + 1] if idx + 1 < len(segs) else None
        except ValueError:
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
