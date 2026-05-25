# Version: 03.14.03
# Phase: PHASE2
"""Playhead overlay widget for the timeline."""

from __future__ import annotations

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush
from PyQt6.QtWidgets import QWidget

from ui.editor.ux.timeline_playhead_mode import playhead_line_color_hex
from ui.style import COLORS


class TimelinePlayheadOverlay(QWidget):
    """Paint the moving playhead without invalidating the heavy timeline body."""

    def __init__(self, timeline, parent=None):
        super().__init__(parent)
        self._timeline = timeline
        self._sec = 0.0
        self._shadow_sec: float | None = None
        self._scroll_x = 0
        self._center_locked = False
        self._busy = False
        self._last_visual_px: int | None = None
        self._last_shadow_visual_px: int | None = None
        self._last_state_signature = None
        self._render_visuals = False
        self._quick = self._create_quick_layer()
        self._shutdown_in_progress = False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

    def _visual_strip_rect(self, *positions: int | None) -> QRect | None:
        xs = [int(pos) for pos in positions if pos is not None]
        if not xs:
            return None
        left = max(0, min(xs) - 12)
        right = min(max(1, self.width()), max(xs) + 13)
        return QRect(left, 0, max(1, right - left), max(1, self.height()))

    def set_state(
        self,
        sec: float,
        scroll_x: int,
        *,
        center_locked: bool = False,
        busy: bool = False,
        shadow_sec: float | None = None,
    ):
        old_px = self._last_visual_px
        old_shadow_px = self._last_shadow_visual_px
        self._sec = max(0.0, float(sec or 0.0))
        self._shadow_sec = None if shadow_sec is None else max(0.0, float(shadow_sec or 0.0))
        self._scroll_x = max(0, int(scroll_x or 0))
        self._center_locked = bool(center_locked)
        self._busy = bool(busy)
        visual_px = int(round(self._playhead_visual_x()))
        shadow_px = None if self._shadow_sec is None else int(round(self._playhead_visual_x_for_sec(self._shadow_sec, center_locked=False)))
        signature = (
            visual_px,
            shadow_px,
            bool(self._center_locked),
            bool(self._busy),
            int(self.width()),
            int(self.height()),
        )
        if signature == getattr(self, "_last_state_signature", None):
            return False
        self._last_visual_px = visual_px
        self._last_shadow_visual_px = shadow_px
        self._last_state_signature = signature
        if not bool(getattr(self, "_render_visuals", False)): return True
        if getattr(self, "_quick", None) is not None:
            self._sync_quick_layer()
            return True
        dirty = self._visual_strip_rect(old_px, visual_px, old_shadow_px, shadow_px)
        if dirty is not None:
            self.update(dirty)
        return True

    def _create_quick_layer(self):
        # A full-viewport QQuickWidget overlay can composite as an opaque black
        # surface on macOS/Metal and hide the classic painter timeline canvas.
        # Keep the playhead on the lightweight QWidget overlay instead.
        return None

    def _playhead_visual_x_for_sec(self, sec: float, *, center_locked: bool) -> float:
        timeline = self._timeline
        canvas = getattr(timeline, "canvas", None)
        if canvas is None:
            return 0.0
        if center_locked:
            return max(0.0, self.width() / 2.0)
        return float(canvas._x(sec) if hasattr(canvas, "_x") else (float(sec or 0.0) * float(getattr(canvas, "pps", 1.0) or 1.0))) - float(self._scroll_x)

    def _playhead_visual_x(self) -> float:
        return self._playhead_visual_x_for_sec(self._sec, center_locked=bool(self._center_locked))

    def _sync_quick_layer(self, quick=None):
        quick = quick or getattr(self, "_quick", None)
        if quick is None:
            return
        timeline = self._timeline
        canvas = getattr(timeline, "canvas", None)
        visible = bool(canvas is not None and float(getattr(canvas, "total_duration", 0.0) or 0.0) > 0)
        line_color = playhead_line_color_hex(getattr(canvas, "focus_mode", None))
        try:
            root = quick.rootObject()
            if root is None:
                return
            root.setProperty("playheadX", float(self._playhead_visual_x()))
            root.setProperty("lineColor", str(line_color))
            root.setProperty("playheadBusy", bool(self._busy))
            root.setProperty("visiblePlayhead", bool(visible))
            root.setProperty("centerLocked", bool(self._center_locked))
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._last_state_signature = None
        quick = getattr(self, "_quick", None)
        if quick is not None:
            quick.setGeometry(self.rect())
            self._sync_quick_layer(quick)
        else:
            self.update()

    def paintEvent(self, event):
        if bool(getattr(self, "_shutdown_in_progress", False)):
            return
        if getattr(self, "_quick", None) is not None:
            return
        timeline = self._timeline
        canvas = getattr(timeline, "canvas", None)
        if canvas is None or float(getattr(canvas, "total_duration", 0.0) or 0.0) <= 0:
            return
        px = int(round(self._playhead_visual_x()))
        shadow_sec = getattr(self, "_shadow_sec", None)
        shadow_px = None if shadow_sec is None else int(round(self._playhead_visual_x_for_sec(shadow_sec, center_locked=False)))
        current_visible = -16 <= px <= self.width() + 16
        shadow_visible = shadow_px is not None and -16 <= shadow_px <= self.width() + 16
        if not current_visible and not shadow_visible:
            return
        painter = QPainter(self)
        if not painter.isActive():
            return
        try:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(event.rect(), Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        except Exception:
            pass
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if shadow_visible:
            shadow_color = QColor(255, 214, 10, 170)
            painter.setPen(QPen(shadow_color, 2, Qt.PenStyle.DashLine))
            painter.drawLine(shadow_px, 0, shadow_px, self.height())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(255, 214, 10, 210), 1))
            painter.drawEllipse(shadow_px - 6, 3, 12, 12)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if current_visible:
            color = QColor(playhead_line_color_hex(getattr(canvas, "focus_mode", None)))
            painter.setPen(QPen(color, 2))
            painter.drawLine(px, 0, px, self.height())
            handle_r = 7
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setBrush(QBrush(QColor("#FF453A" if self._busy else COLORS["warning"])))
            painter.setPen(QPen(QColor("#FFFFFF"), 1))
            painter.drawEllipse(px - handle_r, 2, handle_r * 2, handle_r * 2)
        painter.end()
