# Version: 03.01.06
# Phase: PHASE1-C
"""
ui/timeline_canvas.py
Timeline canvas
"""
import numpy as np
from PyQt6.QtCore import QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QSizePolicy, QWidget

import config

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


class TimelineCanvas(TimelineInlineEditMixin, TimelineInputMixin, TimelinePaintMixin, QWidget):
    seg_clicked             = pyqtSignal(int, float)
    seg_right_clicked       = pyqtSignal(float, QPoint)
    seg_double_clicked      = pyqtSignal(int, float)
    seg_time_changed        = pyqtSignal(int, float, float, str)
    seg_to_gap              = pyqtSignal(int)
    gap_activated           = pyqtSignal(float, float)
    gap_to_segs             = pyqtSignal(float, float)
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
        self.focus_mode = "segment"
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self._ime_preedit = ""
        self.sig_speech_result.connect(self._on_speech_result)
        self._is_listening = False

        self.pps = 200.0
        self.segments:     list[dict] = []
        self.gap_segments: list[dict] = []
        self.vad_segments: list[dict] = []
        self.total_duration: float = 0.0
        self.active_seg_start: float | None = None
        self.playhead_sec: float = 0.0
        self._waveform = None
        self.boundary_times: list[float] = []
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

    # ---------------------------------------------------------
    # State / Utility
    # ---------------------------------------------------------
    def set_zoom(self, new_pps):
        self.pps = max(5.0, min(500.0, new_pps))
        self.update()

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

        if active_sec is not None:
            self.active_seg_start = active_sec

        self.update()

    def set_vad_segments(self, vad_segs):
        self.vad_segments = vad_segs
        self._speech_mask = None      # 마스크 재계산 트리거
        self.update()

    def set_active(self, sec):
        self.active_seg_start = sec
        self.update()

    def set_playhead(self, sec):
        if self.playhead_sec == sec:
            return
        self.playhead_sec = sec
        self.update()

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
            if self._x(seg["start"]) <= x <= self._x(seg["end"]):
                return seg
        return None

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
        widget = self.parent()
        while widget:
            if hasattr(widget, "video_fps"):
                return float(widget.video_fps)
            widget = widget.parent()
        return 30.0

    def _snap_to_frame(self, sec):
        fps = self._get_fps()
        if fps <= 0:
            fps = 30.0
        return round(round(sec * fps) / fps, 3)
