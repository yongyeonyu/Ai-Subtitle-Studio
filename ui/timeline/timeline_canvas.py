# Version: 03.09.18
# Phase: PHASE2
"""
ui/timeline_canvas.py
Timeline canvas
"""
import numpy as np
from PyQt6.QtCore import QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QSizePolicy

import config
from core.frame_time import normalize_fps, snap_sec_to_frame

from ui.timeline.timeline_constants import (
    CANVAS_H,
    HANDLE_R,
    ICON_SZ,
    RULER_H,
    SEG_BOT,
    SEG_TOP,
    WAVE_H,
    WAVE_HALF,
    WAVE_MID,
    _build_gaps,
)
from ui.timeline.timeline_paint import TimelinePaintMixin
from ui.timeline.timeline_input import TimelineInputMixin
from ui.timeline.timeline_inline_edit import TimelineInlineEditMixin
from ui.gpu_rendering import accelerated_widget_base, configure_lightweight_paint, configure_opengl_widget, gpu_backend_name


TimelineCanvasBase = accelerated_widget_base()


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
    diamond_merge           = pyqtSignal(int, int)
    sig_smart_split         = pyqtSignal(int, float, bool)
    sig_speech_result       = pyqtSignal(str)
    speaker_changed         = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.re_recog_zone = None
        self.re_recog_progress = None
        self.setMinimumHeight(CANVAS_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        configure_lightweight_paint(self, opaque=True)
        configure_opengl_widget(self)
        self.render_backend = gpu_backend_name()
        self.focus_mode = "segment"
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self._ime_preedit = ""
        self.sig_speech_result.connect(self._on_speech_result)
        self._is_listening = False

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

    # ---------------------------------------------------------
    # State / Utility
    # ---------------------------------------------------------
    def set_zoom(self, new_pps):
        self.pps = max(5.0, min(500.0, new_pps))
        self.update()

    def set_frame_rate(self, fps: float):
        self.frame_rate = normalize_fps(fps)

    def _invalidate_marker_caches(self):
        self._analysis_markers_cache_key = None
        self._analysis_markers_cache = []
        self._roughcut_major_cache_key = None
        self._roughcut_major_cache = []

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
            len(self.segments),
            len(self.vad_segments),
            len(self.gap_segments),
            round(float(self.total_duration or 0.0), 3),
            tuple((round(float(s.get("start", 0.0) or 0.0), 3), round(float(s.get("end", 0.0) or 0.0), 3), str(s.get("text", "") or ""), str(s.get("quality", "") or "")) for s in self.segments),
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
        self.segments = [s for s in segs if not s.get("is_gap")]
        self.total_duration = total_dur or (segs[-1]["end"] if segs else 0.0)

        new_gaps = _build_gaps(self.segments, self.total_duration)
        old_active = {
            (g["start"], g["end"])
            for g in self.gap_segments
            if g.get("active")
        }

        for gap in new_gaps:
            if (gap["start"], gap["end"]) in old_active:
                gap["active"] = True

        self.gap_segments = new_gaps
        self._refresh_voice_activity_segments()
        self._invalidate_marker_caches()

        if active_sec is not None:
            self.active_seg_start = active_sec
            self._sync_active_segment_key(active_sec)

        self.update()

    def _sync_active_segment_key(self, sec=None, seg=None):
        if seg is None and sec is not None:
            try:
                target = float(sec)
                seg = next(
                    (
                        item for item in self.segments
                        if abs(float(item.get("start", 0.0) or 0.0) - target) < 0.001
                    ),
                    None,
                )
                if seg is None:
                    seg = next(
                        (
                            item for item in self.segments
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
        self.update()

    def set_voice_activity_segments(self, segments: list[dict]):
        self.voice_activity_segments = list(segments or [])
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
        if old_px is None:
            self.update(QRect(max(0, px - 12), 0, 24, CANVAS_H))
        else:
            left = max(0, min(old_px, px) - 12)
            right = min(self.width(), max(old_px, px) + 13)
            self.update(QRect(left, 0, max(1, right - left), CANVAS_H))

    def set_waveform(self, wf):
        self._waveform = wf
        self._speech_mask = None
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
        for seg in self.segments:
            if bool(seg.get("stt_pending") or seg.get("_live_stt_preview")):
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
        left = max(0, min(x1, x2) - int(margin))
        right = min(max(self.width(), self.total_width()), max(x1, x2) + int(margin))
        top = 0 if full_height else max(0, SEG_TOP - 18)
        bottom = CANVAS_H if full_height else CANVAS_H
        return QRect(left, top, max(1, right - left), max(1, bottom - top))

    def _segment_repaint_rect_for_line(self, line_num: int, *, margin: int = 34) -> QRect:
        seg = next((s for s in self.segments if int(s.get("line", -999999)) == int(line_num)), None)
        return self._segment_repaint_rect(seg, margin=margin)

    def _active_segment_repaint_rect(self) -> QRect:
        if getattr(self, "active_seg_start", None) is None and getattr(self, "active_seg_line", None) is None:
            return QRect()
        dirty = QRect()
        for seg in self.segments:
            if self._is_active_segment(seg):
                rect = self._segment_repaint_rect(seg, margin=48)
                dirty = rect if dirty.isNull() else dirty.united(rect)
        return dirty

    def _update_dirty_rect(self, rect: QRect):
        if rect.isValid() and not rect.isEmpty():
            self.update(rect.intersected(QRect(0, 0, max(1, self.width()), max(1, self.height()))))
        else:
            self.update()

    def _get_prev_seg(self, seg):
        segs = sorted(self.segments, key=lambda s: s["start"])
        try:
            idx = segs.index(seg)
            return segs[idx - 1] if idx > 0 else None
        except ValueError:
            return None

    def _get_next_seg(self, seg):
        segs = sorted(self.segments, key=lambda s: s["start"])
        try:
            idx = segs.index(seg)
            return segs[idx + 1] if idx + 1 < len(segs) else None
        except ValueError:
            return None

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
