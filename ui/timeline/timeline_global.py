# Version: 03.14.31
# Phase: PHASE2
"""
ui/timeline_global.py
Global timeline minimap
"""
import numpy as np
from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QSizePolicy

from core.runtime import config
from ui.timeline.timeline_constants import FOCUS_BORDER_COLOR, FOCUS_BORDER_WIDTH
from ui.timeline.timeline_analysis import analysis_markers_for_widget
from ui.gpu_rendering import accelerated_widget_base, configure_lightweight_paint, configure_opengl_widget, gpu_backend_name

GlobalCanvasBase = accelerated_widget_base("timeline")


class GlobalCanvas(GlobalCanvasBase):
    seek_frac = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        configure_lightweight_paint(self, opaque=True)
        configure_opengl_widget(self)
        self.render_backend = gpu_backend_name("timeline")

        self.segments = []
        self.view_start = 0.0
        self.view_end = 1.0
        self.playhead_sec = 0.0
        self.total_duration = 0.0
        self._waveform: np.ndarray | None = None
        self.vad_segments = []
        self._multiclip_boxes = []
        self._whisper_progress_sec = 0.0
        self._clip_label = ''
        self._static_cache: QPixmap | None = None
        self._static_cache_key = None
        self._waveform_columns: list[tuple[int, bool]] = []
        self._last_playhead_px: int | None = None
        self._last_viewport_px: tuple[int, int] | None = None
        self._last_whisper_px: int | None = None

    def _invalidate_static_cache(self):
        self._static_cache = None
        self._static_cache_key = None
        
    def set_whisper_progress(self, sec: float):
        px = self._sec_to_px(sec)
        if self._whisper_progress_sec == sec or self._last_whisper_px == px:
            return
        old_px = self._last_whisper_px
        self._whisper_progress_sec = sec
        self._last_whisper_px = px
        dirty = QRect(0, 0, max(px, old_px or 0) + 3, self.height())
        self.update(dirty)

    def set_waveform(self, wf: np.ndarray):
        self._waveform = wf
        self._waveform_columns = []
        self._invalidate_static_cache()
        self.update()

    def set_vad_segments(self, vad_segs: list):
        self.vad_segments = vad_segs
        self._waveform_columns = []
        self._invalidate_static_cache()
        self.update()

    def set_clip_label(self, text: str):
        self._clip_label = str(text or "")
        self.update()

    def _timeline_has_focus(self) -> bool:
        def _has_focus(widget) -> bool:
            try:
                return bool(widget is not None and hasattr(widget, "hasFocus") and widget.hasFocus())
            except RuntimeError:
                return False

        timeline = self.parent()
        if _has_focus(self) or _has_focus(timeline):
            return True
        for attr in ("canvas", "scroll", "global_canvas"):
            child = getattr(timeline, attr, None) if timeline is not None else None
            if _has_focus(child):
                return True
        return False

    def _draw_focus_bottom(self, p: QPainter):
        if not self._timeline_has_focus():
            return
        p.setPen(QPen(QColor(FOCUS_BORDER_COLOR), FOCUS_BORDER_WIDTH))
        y = max(1, self.height() - FOCUS_BORDER_WIDTH)
        p.drawLine(0, y, self.width(), y)

    def set_playhead(self, sec):
        px = self._sec_to_px(sec)
        if self.playhead_sec == sec or self._last_playhead_px == px:
            return
        self.playhead_sec = sec
        self._last_playhead_px = px
        self.update()

    def update_segments(self, segs, total_dur):
        self.segments = [s for s in segs if not s.get("is_gap")]
        self.total_duration = total_dur
        self._invalidate_static_cache()
        self.update()

    def update_viewport(self, s, e):
        px = (int(max(0.0, min(1.0, s)) * self.width()), int(max(0.0, min(1.0, e)) * self.width()))
        if (self.view_start == s and self.view_end == e) or self._last_viewport_px == px:
            return
        old_px = self._last_viewport_px
        self.view_start = s
        self.view_end = e
        self._last_viewport_px = px
        if old_px is None:
            self.update()
        else:
            left = max(0, min(old_px[0], old_px[1], px[0], px[1]) - 4)
            right = min(self.width(), max(old_px[0], old_px[1], px[0], px[1]) + 5)
            self.update(QRect(left, 0, max(1, right - left), self.height()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._waveform_columns = []
        self._invalidate_static_cache()
        self._last_playhead_px = self._sec_to_px(self.playhead_sec)
        self._last_viewport_px = (
            int(max(0.0, min(1.0, self.view_start)) * self.width()),
            int(max(0.0, min(1.0, self.view_end)) * self.width()),
        )
        self._last_whisper_px = self._sec_to_px(self._whisper_progress_sec)

    def _sec_to_px(self, sec: float) -> int:
        total = float(self.total_duration or 0.0)
        if total <= 0:
            return 0
        return int(max(0.0, float(sec or 0.0)) * self.width() / total)

    def _static_key(self):
        return (
            self.width(),
            self.height(),
            round(float(self.total_duration or 0.0), 3),
            len(self.segments),
            len(self.vad_segments),
            id(self._waveform),
        )

    def _build_waveform_columns(self, width: int, total: float) -> list[tuple[int, bool]]:
        if self._waveform is None or len(self._waveform) <= 0 or width <= 0:
            return []
        if self._waveform_columns and len(self._waveform_columns) == width:
            return self._waveform_columns
        wf = self._waveform
        wf_len = len(wf)
        speech_ranges: list[tuple[int, int]] = []
        if self.vad_segments:
            vad_scale = (wf_len / total) if total and total > 0 else 100.0
            for vs in self.vad_segments:
                try:
                    s_idx = max(0, int(float(vs["start"]) * vad_scale))
                    e_idx = min(wf_len, int(float(vs["end"]) * vad_scale) + 1)
                except Exception:
                    continue
                if e_idx > s_idx:
                    speech_ranges.append((s_idx, e_idx))
        columns: list[tuple[int, bool]] = []
        range_idx = 0
        for x in range(width):
            idx = min(wf_len - 1, int((x / max(1, width)) * wf_len))
            while range_idx < len(speech_ranges) and idx >= speech_ranges[range_idx][1]:
                range_idx += 1
            in_speech = range_idx < len(speech_ranges) and speech_ranges[range_idx][0] <= idx < speech_ranges[range_idx][1]
            columns.append((max(1, int(float(wf[idx]) * 14)), in_speech))
        self._waveform_columns = columns
        return columns

    def _build_static_cache(self) -> QPixmap:
        key = self._static_key()
        if self._static_cache is not None and self._static_cache_key == key:
            return self._static_cache
        pixmap = QPixmap(max(1, self.width()), max(1, self.height()))
        pixmap.fill(QColor("#0B1115"))
        p = QPainter(pixmap)
        w = pixmap.width()
        h = pixmap.height()
        mid_y = h // 2
        total = float(self.total_duration or 0.0)

        markers = analysis_markers_for_widget(
            self,
            list(getattr(self, "segments", []) or []),
            list(getattr(self, "vad_segments", []) or []),
            [],
            total,
        )

        if total > 0 and markers:
            sc = w / max(0.001, total)
            p.setPen(Qt.PenStyle.NoPen)
            for marker in sorted(markers, key=lambda item: int(item.get("priority", 0) or 0)):
                start = max(0.0, float(marker.get("start", 0.0) or 0.0))
                end = max(start, float(marker.get("end", start) or start))
                x = int(start * sc)
                sw = max(1, int((end - start) * sc))
                color = QColor(str(marker.get("color", "#8B949E")))
                color.setAlpha(110 if int(marker.get("priority", 0) or 0) < 80 else 155)
                p.fillRect(QRect(x, 3, sw, h - 6), color)

        columns = self._build_waveform_columns(w, total)
        if columns:
            pen_speech = QPen(QColor(130, 205, 235, 150), 1)
            pen_silence = QPen(QColor(85, 92, 98, 105), 1)
            for x, (amp_h, in_speech) in enumerate(columns):
                p.setPen(pen_speech if in_speech else pen_silence)
                p.drawLine(x, mid_y - amp_h, x, mid_y + amp_h)

        if total > 0:
            sc = w / total
            p.setPen(Qt.PenStyle.NoPen)
            for s in self.segments:
                try:
                    x = int(float(s["start"]) * sc)
                    sw = max(1, int((float(s["end"]) - float(s["start"])) * sc))
                except Exception:
                    continue
                p.fillRect(QRect(x, 14, sw, 18), QColor("#FF453A") if s.get("stt_pending") else QColor("#666666"))

        p.end()
        self._static_cache = pixmap
        self._static_cache_key = key
        return pixmap

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawPixmap(0, 0, self._build_static_cache())

        w = self.width()
        total = float(self.total_duration or 0.0)

        if total <= 0:
            self._draw_focus_bottom(p)
            p.end()
            return
        sc = w / total

        whisper_sec = getattr(self, '_whisper_progress_sec', 0.0)
        if whisper_sec > 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 204, 0, 50))
            wx = int(whisper_sec * sc)
            p.drawRect(0, 0, wx, self.height())

        p.setPen(QPen(QColor(config.ACCENT), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRect(int(self.view_start * w), 1, max(1, int((self.view_end - self.view_start) * w)), 34))

        # 선택 클립 라벨 (우상단 숫자만)
        if self._clip_label:
            p.setPen(QColor("#4FC3F7"))
            p.setFont(QFont("", 11))
            fm = p.fontMetrics()
            txt = str(self._clip_label)
            tw = fm.horizontalAdvance(txt)
            p.drawText(max(4, self.width() - tw - 6), 10, txt)

        # 플레이헤드
        if self.playhead_sec >= 0:
            p.setPen(QPen(QColor("#FF4444"), 2))
            px = int(self.playhead_sec * sc)
            p.drawLine(px, 0, px, self.height())

        self._draw_focus_bottom(p)

    def wheelEvent(self, ev):
        dy = ev.angleDelta().y()
        dx = ev.angleDelta().x()
        delta = -(dy if dy != 0 else dx)

        widget = self.parent()
        while widget:
            if hasattr(widget, "apply_manual_horizontal_scroll_delta"):
                widget.apply_manual_horizontal_scroll_delta(delta // 2)
                ev.accept()
                return
            if hasattr(widget, "scroll"):
                scrollbar = widget.scroll.horizontalScrollBar()
                scrollbar.setValue(scrollbar.value() + delta // 2)
                ev.accept()
                return
            widget = widget.parent()

        ev.ignore()

    def mousePressEvent(self, e):
        self.setFocus()
        frac = max(0.0, min(1.0, e.pos().x() / max(1, self.width())))
        self.seek_frac.emit(frac)

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            frac = max(0.0, min(1.0, e.pos().x() / max(1, self.width())))
            self.seek_frac.emit(frac)
