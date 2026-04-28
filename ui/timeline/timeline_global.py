# Version: 02.07.00
# Phase: PHASE1-D
"""
ui/timeline_global.py
Global timeline minimap
"""
import numpy as np
from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

import config


class GlobalCanvas(QWidget):
    seek_frac = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

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
        
    def set_whisper_progress(self, sec: float):
        if self._whisper_progress_sec == sec:
            return
        self._whisper_progress_sec = sec
        self.update()

    def set_waveform(self, wf: np.ndarray):
        self._waveform = wf
        self.update()

    def set_vad_segments(self, vad_segs: list):
        self.vad_segments = vad_segs
        self.update()

    def set_clip_label(self, text: str):
        self._clip_label = str(text or "")
        self.update()

    def set_playhead(self, sec):
        if self.playhead_sec == sec:
            return
        self.playhead_sec = sec
        self.update()

    def update_segments(self, segs, total_dur):
        self.segments = [s for s in segs if not s.get("is_gap")]
        self.total_duration = total_dur
        self.update()

    def update_viewport(self, s, e):
        if self.view_start == s and self.view_end == e:
            return
        self.view_start = s
        self.view_end = e
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#111111"))

        w = self.width()
        mid_y = self.height() // 2
        total = self.total_duration

        if self._waveform is not None and len(self._waveform) > 0:
            wf_len = len(self._waveform)

            # VAD 기반 speech mask
            speech_mask = np.zeros(wf_len, dtype=bool)
            if self.vad_segments:
                vad_scale = (wf_len / total) if total and total > 0 else 100.0
                for vs in self.vad_segments:
                    s_idx = max(0, int(float(vs["start"]) * vad_scale))
                    e_idx = min(wf_len, int(float(vs["end"]) * vad_scale) + 1)
                    speech_mask[s_idx:e_idx] = True

            for i in range(w):
                idx = int((i / w) * wf_len)
                if idx < wf_len:
                    amp = float(self._waveform[idx])
                    h = max(1, int(amp * 14))
                    if speech_mask[idx]:
                        p.setPen(QPen(QColor(100, 220, 255), 1))   # 파란색 (음성)
                    else:
                        p.setPen(QPen(QColor("#555555"), 1))        # 회색 (무음)
                    p.drawLine(i, mid_y - h, i, mid_y + h)

        if total <= 0:
            p.end()
            return
        sc = w / total

        # ✅ VAD 그린존 오버레이
        if self.vad_segments:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(74, 255, 128, 40))
            for vs in self.vad_segments:
                vx = int(vs["start"] * sc)
                vw = max(1, int((vs["end"] - vs["start"]) * sc))
                p.drawRect(vx, 0, vw, self.height())

        # ✅ Whisper 옐로우존
        whisper_sec = getattr(self, '_whisper_progress_sec', 0.0)
        if whisper_sec > 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 204, 0, 50))
            wx = int(whisper_sec * sc)
            p.drawRect(0, 0, wx, self.height())
        # 자막 세그먼트 블록
        for s in self.segments:
            x = int(s["start"] * sc)
            sw = max(1, int((s["end"] - s["start"]) * sc))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#FF453A") if s.get("stt_pending") else QColor("#666666"))
            p.drawRect(QRect(x, 14, sw, 18))

        # 뷰포트 박스
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

    def wheelEvent(self, ev):
        dy = ev.angleDelta().y()
        dx = ev.angleDelta().x()
        delta = -(dy if dy != 0 else dx)

        widget = self.parent()
        while widget:
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
