# Version: 03.14.31
# Phase: PHASE2
"""
ui/timeline_global.py
Global timeline minimap
"""
import numpy as np
from PyQt6.QtCore import QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QSizePolicy, QWidget

from core.runtime import config
from ui.timeline.timeline_constants import FOCUS_BORDER_COLOR, FOCUS_BORDER_WIDTH
from ui.timeline.timeline_analysis import (
    preliminary_major_markers_for_widget,
    roughcut_major_markers_for_widget,
    topicless_major_markers_for_widget,
)
from ui.dialogs.qml_popup import show_context_menu
from ui.gpu_rendering import configure_lightweight_paint
from ui.ux.apple_black_palette import APPLE_BLACK_MINIMAP

GLOBAL_TIMELINE_RENDER_BACKEND_2D = "qwidget-2d"
GlobalCanvasBase = QWidget

MINIMAP_BG = APPLE_BLACK_MINIMAP["bg"]
MINIMAP_TOP_LANE_BG = APPLE_BLACK_MINIMAP["top_lane_bg"]
MINIMAP_BOTTOM_LANE_BG = APPLE_BLACK_MINIMAP["bottom_lane_bg"]
MINIMAP_DIVIDER = QColor(APPLE_BLACK_MINIMAP["divider"])
MINIMAP_MAJOR_BORDER = QColor(APPLE_BLACK_MINIMAP["major_border"])
MINIMAP_PRELIMINARY_LANE_BG = APPLE_BLACK_MINIMAP["preliminary_lane_bg"]
MINIMAP_REFERENCE_LANE_BG = APPLE_BLACK_MINIMAP["reference_lane_bg"]
MINIMAP_SUBTITLE_LANE_BG = APPLE_BLACK_MINIMAP["subtitle_lane_bg"]
MINIMAP_SILENCE_LANE_BG = APPLE_BLACK_MINIMAP["silence_lane_bg"]
MINIMAP_SUBTITLE_FILL = QColor(*APPLE_BLACK_MINIMAP["subtitle_fill_rgba"])
MINIMAP_SUBTITLE_BORDER = QColor(APPLE_BLACK_MINIMAP["subtitle_border"])
MINIMAP_PENDING_FILL = QColor(*APPLE_BLACK_MINIMAP["pending_fill_rgba"])
MINIMAP_PENDING_BORDER = QColor(APPLE_BLACK_MINIMAP["pending_border"])
MINIMAP_SUBTITLE_MERGE_GAP_PX = 4
MINIMAP_MARKER_LANE_H = 28
MINIMAP_HEIGHT = 104


class GlobalCanvas(GlobalCanvasBase):
    seek_frac = pyqtSignal(float)
    roughcut_llm_run_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMinimumHeight(MINIMAP_HEIGHT)
        self.resize(max(1, self.width()), MINIMAP_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        configure_lightweight_paint(self, opaque=True)
        # 미니맵도 2D 단일 렌더러로 맞춰 메인 타임라인과 다른 합성 경로를 만들지 않는다.
        self._single_owner_2d_renderer = True
        self.render_backend = GLOBAL_TIMELINE_RENDER_BACKEND_2D

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
        self._segments_signature = None

    def sizeHint(self) -> QSize:
        return QSize(1, MINIMAP_HEIGHT)

    def minimumSizeHint(self) -> QSize:
        return QSize(1, MINIMAP_HEIGHT)

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

    def update_segments(self, segs, total_dur, *, signature=None, rows=None):
        if rows is None:
            rows = [s for s in segs if not s.get("is_gap")]
        if signature is None:
            checksum = 0
            for seg in rows:
                try:
                    start_ms = int(round(float(seg.get("start", 0.0) or 0.0) * 1000.0))
                    end_ms = int(round(float(seg.get("end", seg.get("start", 0.0)) or 0.0) * 1000.0))
                except Exception:
                    start_ms = 0
                    end_ms = 0
                checksum = ((checksum * 1000003) ^ (start_ms * 31) ^ end_ms) & 0xFFFFFFFF
            signature = (len(rows), int(round(float(total_dur or 0.0) * 1000.0)), checksum)
        if signature == getattr(self, "_segments_signature", None):
            self.segments = rows
            self.total_duration = total_dur
            return
        self._segments_signature = signature
        self.segments = rows
        self.total_duration = total_dur
        self._invalidate_static_cache()
        self.update()

    def update_viewport(self, s, e):
        px = (int(max(0.0, min(1.0, s)) * self.width()), int(max(0.0, min(1.0, e)) * self.width()))
        if (self.view_start == s and self.view_end == e) or self._last_viewport_px == px:
            return
        self.view_start = s
        self.view_end = e
        self._last_viewport_px = px
        self.update()

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
        major_signature = tuple(
            (
                round(float(marker.get("start", 0.0) or 0.0), 3),
                round(float(marker.get("end", marker.get("start", 0.0)) or 0.0), 3),
                str(marker.get("display_label", "") or marker.get("label", "") or ""),
                str(marker.get("color", "") or ""),
                str(marker.get("status", "") or ""),
            )
            for marker in roughcut_major_markers_for_widget(self)
        )
        preliminary_signature = tuple(
            (
                round(float(marker.get("start", 0.0) or 0.0), 3),
                round(float(marker.get("end", marker.get("start", 0.0)) or 0.0), 3),
                str(marker.get("display_label", "") or marker.get("label", "") or ""),
                str(marker.get("color", "") or ""),
                str(marker.get("status", "") or ""),
            )
            for marker in preliminary_major_markers_for_widget(self)
        )
        topicless_signature = tuple(
            (
                round(float(marker.get("start", 0.0) or 0.0), 3),
                round(float(marker.get("end", marker.get("start", 0.0)) or 0.0), 3),
                str(marker.get("display_label", "") or marker.get("label", "") or ""),
                str(marker.get("color", "") or ""),
                str(marker.get("status", "") or ""),
            )
            for marker in topicless_major_markers_for_widget(self)
        )
        return (
            self.width(),
            self.height(),
            round(float(self.total_duration or 0.0), 3),
            len(self.segments),
            len(self.vad_segments),
            id(self._waveform),
            major_signature,
            preliminary_signature,
            topicless_signature,
        )

    def _build_waveform_columns(self, width: int, total: float) -> list[tuple[int, bool]]:
        if self._waveform is None or len(self._waveform) <= 0 or width <= 0:
            return []
        if self._waveform_columns and len(self._waveform_columns) == width:
            return self._waveform_columns
        wf = self._waveform
        try:
            from core.native_swift_timeline import build_waveform_columns_via_swift

            native_columns = build_waveform_columns_via_swift(
                wf,
                width=width,
                total_duration=total,
                vad_segments=list(self.vad_segments or []),
            )
            if native_columns is not None and len(native_columns) == width:
                self._waveform_columns = native_columns
                return native_columns
        except Exception:
            pass
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

    def _merged_minimap_subtitle_segments(self, width: int, total: float) -> list[dict]:
        rows: list[dict] = []
        if width <= 0 or total <= 0:
            return rows
        max_gap_sec = float(MINIMAP_SUBTITLE_MERGE_GAP_PX) * float(total) / float(max(1, width))
        for seg in sorted(list(self.segments or []), key=lambda item: float(item.get("start", 0.0) or 0.0)):
            try:
                start = max(0.0, float(seg.get("start", 0.0) or 0.0))
                end = max(start, float(seg.get("end", start) or start))
            except Exception:
                continue
            pending = bool(seg.get("stt_pending"))
            text = str(seg.get("text", "") or "").strip()
            if rows:
                prev = rows[-1]
                if pending == bool(prev.get("stt_pending")) and start <= float(prev.get("end", 0.0) or 0.0) + max_gap_sec:
                    prev["end"] = max(float(prev.get("end", 0.0) or 0.0), end)
                    if text:
                        prev_text = str(prev.get("text", "") or "").strip()
                        if text not in prev_text:
                            prev["text"] = f"{prev_text} {text}".strip() if prev_text else text
                    prev["count"] = int(prev.get("count", 1) or 1) + 1
                    continue
            rows.append(
                {
                    "start": start,
                    "end": end,
                    "stt_pending": pending,
                    "text": text,
                    "count": 1,
                }
            )
        return rows

    def _build_static_cache(self) -> QPixmap:
        key = self._static_key()
        if self._static_cache is not None and self._static_cache_key == key:
            return self._static_cache
        if bool(getattr(self, "_shutdown_in_progress", False)):
            return QPixmap()
        pixmap = QPixmap(max(1, self.width()), max(1, self.height()))
        pixmap.fill(QColor(MINIMAP_BG))
        p = QPainter(pixmap)
        if not p.isActive():
            return pixmap
        w = pixmap.width()
        h = pixmap.height()
        total = float(self.total_duration or 0.0)
        marker_lane_h = max(22, min(int(MINIMAP_MARKER_LANE_H), max(1, h - 24)))
        top_lane = QRect(0, 0, w, marker_lane_h)
        bottom_lane = QRect(0, top_lane.bottom() + 1, w, max(1, h - top_lane.height() - 1))
        divider_y = top_lane.bottom() + 1

        p.fillRect(top_lane, QColor(MINIMAP_TOP_LANE_BG))
        p.fillRect(bottom_lane, QColor(MINIMAP_BOTTOM_LANE_BG))
        p.setPen(QPen(MINIMAP_DIVIDER, 1))
        p.drawLine(0, divider_y, w, divider_y)
        p.drawRect(QRect(0, 0, max(1, w - 1), max(1, h - 1)))

        def _rect_for_lane(start: float, end: float, lane: QRect, *, min_h_pad: int = 1) -> QRect:
            if total <= 0:
                return QRect()
            x = int(start * (w / total))
            sw = max(1, int((end - start) * (w / total)))
            return QRect(
                x,
                lane.y() + min_h_pad,
                sw,
                max(1, lane.height() - (min_h_pad * 2)),
            )

        preliminary_markers = preliminary_major_markers_for_widget(self)
        topicless_markers = topicless_major_markers_for_widget(self)
        major_markers = roughcut_major_markers_for_widget(self)
        if total > 0 and preliminary_markers:
            preview_lane = QRect(top_lane.x(), top_lane.y(), top_lane.width(), max(1, top_lane.height() // 2))
            reference_lane = QRect(
                top_lane.x(),
                preview_lane.bottom() + 1,
                top_lane.width(),
                max(1, top_lane.height() - preview_lane.height() - 1),
            )
            p.fillRect(preview_lane, QColor(MINIMAP_PRELIMINARY_LANE_BG))
            p.fillRect(reference_lane, QColor(MINIMAP_REFERENCE_LANE_BG))
            p.setPen(QPen(MINIMAP_DIVIDER, 1))
            p.drawLine(0, reference_lane.y() - 1, w, reference_lane.y() - 1)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            for marker in preliminary_markers:
                try:
                    start = max(0.0, float(marker.get("start", 0.0) or 0.0))
                    end = max(start, float(marker.get("end", start) or start))
                except Exception:
                    continue
                rect = _rect_for_lane(start, end, preview_lane, min_h_pad=1)
                if rect.isEmpty():
                    continue
                border = QColor(str(marker.get("color", MINIMAP_MAJOR_BORDER.name())))
                fill = QColor(border)
                fill.setAlpha(70)
                p.setBrush(fill)
                p.setPen(QPen(border, 1))
                rounded = QRectF(rect.adjusted(0, 0, -1, -1))
                radius = max(1.5, min(4.0, rounded.height() / 2.3))
                p.drawRoundedRect(rounded, radius, radius)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for marker in topicless_markers:
                try:
                    start = max(0.0, float(marker.get("start", 0.0) or 0.0))
                    end = max(start, float(marker.get("end", start) or start))
                except Exception:
                    continue
                rect = _rect_for_lane(start, end, reference_lane, min_h_pad=1)
                if rect.isEmpty():
                    continue
                border = QColor(str(marker.get("color", MINIMAP_MAJOR_BORDER.name())))
                border.setAlpha(215)
                p.setPen(QPen(border, 1))
                rounded = QRectF(rect.adjusted(0, 0, -1, -1))
                radius = max(1.5, min(4.0, rounded.height() / 2.3))
                p.drawRoundedRect(rounded, radius, radius)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        elif total > 0 and major_markers:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for marker in major_markers:
                try:
                    start = max(0.0, float(marker.get("start", 0.0) or 0.0))
                    end = max(start, float(marker.get("end", start) or start))
                except Exception:
                    continue
                rect = _rect_for_lane(start, end, top_lane, min_h_pad=1)
                if rect.isEmpty():
                    continue
                border = QColor(str(marker.get("color", MINIMAP_MAJOR_BORDER.name())))
                p.setPen(QPen(border, 1))
                rounded = QRectF(rect.adjusted(0, 0, -1, -1))
                radius = max(2.0, min(4.0, rounded.height() / 2.4))
                p.drawRoundedRect(rounded, radius, radius)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        if total > 0:
            subtitle_lane = bottom_lane
            p.fillRect(subtitle_lane, QColor(MINIMAP_SUBTITLE_LANE_BG))
            p.setPen(Qt.PenStyle.NoPen)
            pending_rects: list[QRect] = []
            confirmed_rects: list[QRect] = []
            for s in self._merged_minimap_subtitle_segments(w, total):
                rect = _rect_for_lane(
                    float(s.get("start", 0.0) or 0.0),
                    float(s.get("end", 0.0) or 0.0),
                    subtitle_lane,
                    min_h_pad=1,
                )
                if s.get("stt_pending"):
                    pending_rects.append(rect)
                else:
                    confirmed_rects.append(rect)
            if confirmed_rects:
                p.setBrush(MINIMAP_SUBTITLE_FILL)
                p.drawRects(confirmed_rects)
                p.setPen(QPen(MINIMAP_SUBTITLE_BORDER, 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRects(confirmed_rects)
            if pending_rects:
                p.setBrush(MINIMAP_PENDING_FILL)
                p.drawRects(pending_rects)
                p.setPen(QPen(MINIMAP_PENDING_BORDER, 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRects(pending_rects)

        p.end()
        self._static_cache = pixmap
        self._static_cache_key = key
        return pixmap

    def paintEvent(self, event):
        if bool(getattr(self, "_shutdown_in_progress", False)):
            return
        p = QPainter(self)
        if not p.isActive():
            return
        static_cache = self._build_static_cache()
        if not static_cache.isNull():
            p.drawPixmap(0, 0, static_cache)

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
        p.drawRect(QRect(int(self.view_start * w), 1, max(1, int((self.view_end - self.view_start) * w)), max(1, self.height() - 3)))

        # 선택 클립 라벨 (우상단 숫자만)
        if self._clip_label:
            p.setPen(QColor("#4FC3F7"))
            p.setFont(QFont(config.FONT, 11))
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

    def _event_global_pos(self, event):
        try:
            return event.globalPosition().toPoint()
        except Exception:
            return event.globalPos()

    def _show_context_menu(self, event) -> bool:
        items = [
            {
                "id": "roughcut_llm",
                "label": "러프컷 LLM 실행",
                "accent": "#5AC8FA",
            },
        ]
        chosen = show_context_menu(self, self._event_global_pos(event), items)
        if chosen == "roughcut_llm":
            self.roughcut_llm_run_requested.emit()
            return True
        return False

    def mousePressEvent(self, e):
        self.setFocus()
        if e.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(e)
            e.accept()
            return
        frac = max(0.0, min(1.0, e.pos().x() / max(1, self.width())))
        self.seek_frac.emit(frac)

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            frac = max(0.0, min(1.0, e.pos().x() / max(1, self.width())))
            self.seek_frac.emit(frac)
