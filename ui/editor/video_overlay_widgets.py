# Version: 03.13.04
# Phase: PHASE2
"""Video preview thumbnail surface and subtitle overlay widgets."""

from __future__ import annotations

import json
import os

from PyQt6.QtWidgets import QLabel, QSizePolicy, QGraphicsView, QGraphicsScene, QGraphicsItem, QWidget
from PyQt6.QtCore import Qt, QRectF, QSizeF, QUrl
from PyQt6.QtGui import QFont, QColor, QPainter, QFontMetrics, QBrush, QPixmap, QFontDatabase
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem

from core.runtime import config
from ui.gpu_rendering import gpu_backend_name, make_accelerated_viewport, scenegraph_enabled


def _available_font_family(preferred: str, fallback: str = "Apple SD Gothic Neo") -> str:
    preferred = str(preferred or "").strip()
    families = set(QFontDatabase.families())
    if preferred in families:
        return preferred
    if preferred.startswith("Pretendard"):
        for candidate in ("Pretendard", "Pretendard Regular", fallback):
            if candidate in families:
                return candidate
    return fallback if fallback in families else (preferred or fallback)


class ThumbnailLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._scaled_cache = None
        self._scaled_cache_size = None
        self.setStyleSheet("background: #000000;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self._scaled_cache = None
        self._scaled_cache_size = None
        self.update()

    def paintEvent(self, event):
        if self._pixmap and not self._pixmap.isNull():
            painter = QPainter(self)
            cache_size = (self.width(), self.height(), self._pixmap.cacheKey())
            if self._scaled_cache is None or self._scaled_cache_size != cache_size:
                self._scaled_cache = self._pixmap.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self._scaled_cache_size = cache_size
            scaled = self._scaled_cache
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            super().paintEvent(event)

    def resizeEvent(self, event):
        self._scaled_cache = None
        self._scaled_cache_size = None
        super().resizeEvent(event)


def _qcolor_from_style(style: dict, key: str, default: str) -> QColor:
    return QColor(str((style or {}).get(key, default)))


def _output_metrics_for_style(style: dict) -> tuple[int, float]:
    res = str((style or {}).get("res", "FHD (1920px)") or "")
    output_width = 3840 if ("3840" in res or "4K" in res.upper() or "UHD" in res.upper()) else 1920
    res_scale = 4.0 if output_width >= 3840 else 2.0
    return output_width, res_scale


def _load_export_dialog_style() -> dict:
    try:
        settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                style = json.load(f).get("export_dialog", {}) or {}
                if isinstance(style, dict):
                    return dict(style)
    except Exception:
        pass
    return {"res": "FHD (1920px)", "size": "22", "align": "가운데"}


def _wrap_overlay_text_lines(text: str, fm: QFontMetrics, max_width: int) -> list[str]:
    max_width = max(24, int(max_width))
    wrapped: list[str] = []
    for raw_line in str(text or "").replace("\u2028", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            wrapped.append("")
            continue
        words = line.split()
        if not words:
            words = list(line)
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if fm.horizontalAdvance(candidate) <= max_width:
                current = candidate
                continue
            if current:
                wrapped.append(current)
                current = ""
            if fm.horizontalAdvance(word) <= max_width:
                current = word
                continue
            chunk = ""
            for ch in word:
                candidate = f"{chunk}{ch}"
                if chunk and fm.horizontalAdvance(candidate) > max_width:
                    wrapped.append(chunk)
                    chunk = ch
                else:
                    chunk = candidate
            current = chunk
        if current:
            wrapped.append(current)
    return wrapped or [""]


def paint_subtitle_overlay(painter: QPainter, bounds: QRectF, text: str, style: dict | None):
    if not text:
        return
    style = dict(style or {})
    text = str(text or "").replace("\u2028", "\n")
    width = max(1, int(bounds.width()))
    height = max(1, int(bounds.height()))
    left = float(bounds.left())
    top = float(bounds.top())

    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    try:
        base_size = int(style.get("size", 22))
    except Exception:
        base_size = 22
    output_width, res_scale = _output_metrics_for_style(style)
    preview_scale = max(0.01, width / max(1.0, float(output_width)))
    font_px = max(4, int(base_size * res_scale * preview_scale))

    font = QFont(_available_font_family(style.get("font", "Apple SD Gothic Neo")))
    font.setPixelSize(font_px)
    if style.get("bold", True):
        font.setWeight(QFont.Weight.Bold)
    painter.setFont(font)
    fm = QFontMetrics(font)

    max_text_w = int(width * float(style.get("max_text_width_ratio", 0.92) or 0.92))
    lines = _wrap_overlay_text_lines(text, fm, max_text_w)
    line_h = fm.height()
    text_w = max((fm.horizontalAdvance(ln) for ln in lines), default=0)
    try:
        line_spacing = int(style.get("lsp", 6) or 6)
    except Exception:
        line_spacing = 6
    lsp = max(1, int(line_spacing * res_scale * preview_scale))
    text_h = line_h * len(lines) + lsp * max(0, len(lines) - 1)

    align = style.get("align", "가운데")
    if align == "왼쪽":
        x = left + int(width * 0.04)
    elif align == "오른쪽":
        x = left + width - text_w - int(width * 0.04)
    else:
        x = left + (width - text_w) / 2
    y = top + max(8, height - text_h - int(height * 0.11))

    if style.get("bg", False):
        bg_c = _qcolor_from_style(style, "bg_c", "#000000")
        try:
            bg_c.setAlpha(int(int(style.get("bg_op", 50)) * 2.55))
        except Exception:
            bg_c.setAlpha(128)
        margin = max(1, int(int(style.get("bg_margin", 18)) * res_scale * preview_scale))
        radius = max(1, int(int(style.get("bg_radius", 10)) * res_scale * preview_scale))
        painter.setBrush(QBrush(bg_c))
        painter.setPen(Qt.PenStyle.NoPen)
        if style.get("bg_full", False):
            painter.drawRect(QRectF(left, y - margin // 2, width, text_h + margin))
        else:
            painter.drawRoundedRect(
                QRectF(x - margin, y - margin // 2, text_w + margin * 2, text_h + margin),
                radius,
                radius,
            )

    if style.get("shadow", False):
        shadow = _qcolor_from_style(style, "shd_c", "#000000")
        shadow.setAlpha(200)
        try:
            sx = int(int(style.get("shdx", 3)) * res_scale * preview_scale)
            sy = int(int(style.get("shdy", 3)) * res_scale * preview_scale)
        except Exception:
            sx, sy = 2, 2
        painter.setPen(shadow)
        curr_y = y
        for ln in lines:
            lw = fm.horizontalAdvance(ln)
            lx = x if align == "왼쪽" else (x + text_w - lw if align == "오른쪽" else x + (text_w - lw) / 2)
            painter.drawText(int(lx + sx), int(curr_y + fm.ascent() + sy), ln)
            curr_y += line_h + lsp

    if not style.get("no_bdr", False):
        try:
            border_w = max(0, int(int(style.get("bdr_w", 2)) * res_scale * preview_scale))
        except Exception:
            border_w = 1
        if border_w > 0:
            painter.setPen(_qcolor_from_style(style, "bdr_c", "#FFFFFF"))
            for dx in range(-border_w, border_w + 1):
                for dy in range(-border_w, border_w + 1):
                    if dx == 0 and dy == 0:
                        continue
                    curr_y = y
                    for ln in lines:
                        lw = fm.horizontalAdvance(ln)
                        lx = x if align == "왼쪽" else (x + text_w - lw if align == "오른쪽" else x + (text_w - lw) / 2)
                        painter.drawText(int(lx + dx), int(curr_y + fm.ascent() + dy), ln)
                        curr_y += line_h + lsp

    painter.setPen(_qcolor_from_style(style, "txt_c", "#FFFFFF"))
    curr_y = y
    for ln in lines:
        lw = fm.horizontalAdvance(ln)
        lx = x if align == "왼쪽" else (x + text_w - lw if align == "오른쪽" else x + (text_w - lw) / 2)
        painter.drawText(int(lx), int(curr_y + fm.ascent()), ln)
        curr_y += line_h + lsp


class SubtitleSceneOverlayItem(QGraphicsItem):
    """Subtitle overlay rendered inside the video scene/GL viewport."""

    def __init__(self):
        super().__init__()
        self._rect = QRectF()
        self._text = ""
        self._style: dict = _load_export_dialog_style()
        self.setZValue(20)

    def boundingRect(self):
        return self._rect

    def set_rect(self, rect):
        next_rect = QRectF(rect)
        if self._rect == next_rect:
            return
        self.prepareGeometryChange()
        self._rect = next_rect
        self.update()

    def set_text(self, text: str):
        text = str(text or "")
        if self._text == text:
            return
        self._text = text
        self.setVisible(bool(text))
        self.update()

    def text(self) -> str:
        return self._text

    def set_export_style(self, style: dict | None):
        next_style = dict(style or {})
        if self._style == next_style:
            return
        self._style = next_style
        self.update()

    def paint(self, painter, _option, widget=None):
        paint_subtitle_overlay(painter, self._rect, self._text, self._style)


class VideoSurfaceView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.video_item = QGraphicsVideoItem()
        self.video_item.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self._scene.addItem(self.video_item)
        self.subtitle_item = SubtitleSceneOverlayItem()
        self.subtitle_item.setVisible(False)
        self._scene.addItem(self.subtitle_item)
        self.setScene(self._scene)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        viewport = make_accelerated_viewport(self, feature="video")
        if viewport is not None:
            self.setViewport(viewport)
            self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.render_backend = gpu_backend_name()
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState, True)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheNone)
        self.setStyleSheet("background: #000000; border: none;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_video_display_rect(self, rect):
        rect = QRectF(rect)
        self.video_item.setPos(rect.left(), rect.top())
        self.video_item.setSize(QSizeF(max(1.0, rect.width()), max(1.0, rect.height())))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = QRectF(0, 0, self.viewport().width(), self.viewport().height())
        self._scene.setSceneRect(rect)
        self.set_video_display_rect(rect)


class SubtitleQuickOverlay(QWidget):
    """QML/SceneGraph subtitle overlay for the video preview."""

    @classmethod
    def create(cls, parent=None):
        if not scenegraph_enabled("video"):
            return None
        qml_path = os.path.join(os.path.dirname(__file__), "video_subtitle_overlay.qml")
        if not os.path.exists(qml_path):
            return None
        try:
            return cls(qml_path, parent)
        except Exception:
            return None

    def __init__(self, qml_path: str, parent=None):
        super().__init__(parent)
        try:
            from PyQt6.QtQuickWidgets import QQuickWidget
        except Exception as exc:
            raise RuntimeError("QQuickWidget is unavailable") from exc
        self._text = ""
        self._style = _load_export_dialog_style()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAutoFillBackground(False)
        self._quick = QQuickWidget(self)
        self._quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self._quick.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._quick.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._quick.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._quick.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._quick.setClearColor(QColor(0, 0, 0, 0))
        self._quick.setSource(QUrl.fromLocalFile(qml_path))
        if self._quick.status() == QQuickWidget.Status.Error:
            raise RuntimeError("video subtitle QML failed to load")
        self._quick.show()
        self._sync_root()
        self.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._quick.setGeometry(self.rect())

    def set_text(self, text: str):
        text = str(text or "")
        if self._text == text:
            return
        self._text = text
        self.setVisible(bool(text))
        self._sync_root()

    def text(self) -> str:
        return self._text

    def set_export_style(self, style: dict | None):
        next_style = dict(style or {})
        if self._style == next_style:
            return
        self._style = next_style
        self._sync_root()

    def _sync_root(self):
        try:
            root = self._quick.rootObject()
            if root is None:
                return
            root.setProperty("subtitleText", self._text)
            root.setProperty("styleData", dict(self._style or {}))
        except Exception:
            pass


class SubtitleLabel(QLabel):
    """비디오 프리뷰 위에 출력 설정을 반영해 그리는 자막 overlay."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(False)
        self._export_style = {}
        self.refresh_export_style()

    def refresh_export_style(self):
        try:
            settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    self._export_style = json.load(f).get("export_dialog", {}) or {}
                    if not isinstance(self._export_style, dict):
                        self._export_style = {}
        except Exception:
            self._export_style = _load_export_dialog_style()
        if not self._export_style:
            self._export_style = _load_export_dialog_style()

    def set_export_style(self, style: dict | None):
        self._export_style = dict(style or {})
        self.update()

    def setText(self, text):
        super().setText(text)

    def _qcolor(self, key, default):
        return QColor(str(self._export_style.get(key, default)))

    def _output_metrics(self):
        res = str(self._export_style.get("res", "FHD (1920px)") or "")
        output_width = 3840 if ("3840" in res or "4K" in res.upper() or "UHD" in res.upper()) else 1920
        res_scale = 4.0 if output_width >= 3840 else 2.0
        return output_width, res_scale

    def _wrap_text_lines(self, text: str, fm: QFontMetrics, max_width: int) -> list[str]:
        max_width = max(24, int(max_width))
        wrapped: list[str] = []
        for raw_line in str(text or "").replace("\u2028", "\n").split("\n"):
            line = raw_line.strip()
            if not line:
                wrapped.append("")
                continue
            words = line.split()
            if not words:
                words = list(line)
            current = ""
            for word in words:
                candidate = word if not current else f"{current} {word}"
                if fm.horizontalAdvance(candidate) <= max_width:
                    current = candidate
                    continue
                if current:
                    wrapped.append(current)
                    current = ""
                if fm.horizontalAdvance(word) <= max_width:
                    current = word
                    continue
                chunk = ""
                for ch in word:
                    candidate = f"{chunk}{ch}"
                    if chunk and fm.horizontalAdvance(candidate) > max_width:
                        wrapped.append(chunk)
                        chunk = ch
                    else:
                        chunk = candidate
                current = chunk
            if current:
                wrapped.append(current)
        return wrapped or [""]

    def paintEvent(self, event):
        text = self.text()
        if not text:
            return

        # \u2028을 \n으로 치환하여 줄 나눔 처리
        text = text.replace('\u2028', '\n')

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        style = self._export_style
        try:
            base_size = int(style.get("size", 22))
        except Exception:
            base_size = 22
        output_width, res_scale = self._output_metrics()
        preview_scale = max(0.01, self.width() / max(1.0, float(output_width)))
        font_px = max(4, int(base_size * res_scale * preview_scale))

        font = QFont(_available_font_family(style.get("font", "Apple SD Gothic Neo")))
        font.setPixelSize(font_px)
        if style.get("bold", True):
            font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)

        max_text_w = int(self.width() * float(style.get("max_text_width_ratio", 0.92) or 0.92))
        lines = self._wrap_text_lines(text, fm, max_text_w)
        line_h = fm.height()
        text_w = max((fm.horizontalAdvance(ln) for ln in lines), default=0)
        try:
            line_spacing = int(style.get("lsp", 6) or 6)
        except Exception:
            line_spacing = 6
        lsp = max(1, int(line_spacing * res_scale * preview_scale))
        text_h = line_h * len(lines) + lsp * max(0, len(lines) - 1)

        align = style.get("align", "가운데")
        if align == "왼쪽":
            x = int(self.width() * 0.04)
        elif align == "오른쪽":
            x = self.width() - text_w - int(self.width() * 0.04)
        else:
            x = (self.width() - text_w) / 2
        y = max(8, self.height() - text_h - int(self.height() * 0.11))

        if style.get("bg", False):
            bg_c = self._qcolor("bg_c", "#000000")
            try:
                bg_c.setAlpha(int(int(style.get("bg_op", 50)) * 2.55))
            except Exception:
                bg_c.setAlpha(128)
            margin = max(1, int(int(style.get("bg_margin", 18)) * res_scale * preview_scale))
            radius = max(1, int(int(style.get("bg_radius", 10)) * res_scale * preview_scale))
            painter.setBrush(QBrush(bg_c))
            painter.setPen(Qt.PenStyle.NoPen)
            if style.get("bg_full", False):
                painter.drawRect(QRectF(0, y - margin // 2, self.width(), text_h + margin))
            else:
                painter.drawRoundedRect(
                    QRectF(x - margin, y - margin // 2, text_w + margin * 2, text_h + margin),
                    radius,
                    radius,
                )

        if style.get("shadow", False):
            shadow = self._qcolor("shd_c", "#000000")
            shadow.setAlpha(200)
            try:
                sx = int(int(style.get("shdx", 3)) * res_scale * preview_scale)
                sy = int(int(style.get("shdy", 3)) * res_scale * preview_scale)
            except Exception:
                sx, sy = 2, 2
            painter.setPen(shadow)
            curr_y = y
            for ln in lines:
                lw = fm.horizontalAdvance(ln)
                lx = x if align == "왼쪽" else (x + text_w - lw if align == "오른쪽" else x + (text_w - lw) / 2)
                painter.drawText(int(lx + sx), int(curr_y + fm.ascent() + sy), ln)
                curr_y += line_h + lsp

        if not style.get("no_bdr", False):
            try:
                border_w = max(0, int(int(style.get("bdr_w", 2)) * res_scale * preview_scale))
            except Exception:
                border_w = 1
            if border_w > 0:
                painter.setPen(self._qcolor("bdr_c", "#FFFFFF"))
                for dx in range(-border_w, border_w + 1):
                    for dy in range(-border_w, border_w + 1):
                        if dx == 0 and dy == 0:
                            continue
                        curr_y = y
                        for ln in lines:
                            lw = fm.horizontalAdvance(ln)
                            lx = x if align == "왼쪽" else (x + text_w - lw if align == "오른쪽" else x + (text_w - lw) / 2)
                            painter.drawText(int(lx + dx), int(curr_y + fm.ascent() + dy), ln)
                            curr_y += line_h + lsp

        painter.setPen(self._qcolor("txt_c", "#FFFFFF"))
        curr_y = y
        for ln in lines:
            lw = fm.horizontalAdvance(ln)
            lx = x if align == "왼쪽" else (x + text_w - lw if align == "오른쪽" else x + (text_w - lw) / 2)
            painter.drawText(int(lx), int(curr_y + fm.ascent()), ln)
            curr_y += line_h + lsp
