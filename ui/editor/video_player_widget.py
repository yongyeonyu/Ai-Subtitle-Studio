# Version: 03.09.07
# Phase: PHASE2
"""
ui/video_player_widget.py - PyQt6 비디오 플레이어
[v01.00.01 버그수정] _get_audio_ai_setting: 미정의 변수 'paths' 참조 오류 제거
"""
import os
import json
import hashlib
import subprocess
import tempfile
import time
from bisect import bisect_right

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QSizePolicy, QStackedWidget,
                             QGraphicsView, QGraphicsScene, QGraphicsItem)
from PyQt6.QtCore import Qt, QTimer, QRectF, QUrl, QSizeF, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPainter, QFontMetrics, QBrush, QPainterPath, QPen, QPixmap, QFontDatabase, QImage

from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem

import config
from core.frame_time import build_frame_time_map, normalize_fps, snap_sec_to_frame
from core.roughcut import default_thumbnail_cache_dir, ensure_thumbnail
from ui.gpu_rendering import gpu_backend_name, make_accelerated_viewport


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

    def paint(self, painter, option, widget=None):
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
        viewport = make_accelerated_viewport(self)
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


class _WorkerProxy:
    def __init__(self, parent_widget):
        self.parent_widget = parent_widget
        self.media_player = parent_widget.media_player
        
    @property
    def _play(self): return self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        
    @_play.setter
    def _play(self, value): pass 

    def set_playing(self, playing: bool):
        if playing: 
            self.media_player.play()
            if getattr(self.parent_widget, 'has_vocal_track', False):
                self.parent_widget.vocal_player.setPosition(self.media_player.position())
                self.parent_widget.vocal_player.play()
        else: 
            self.media_player.pause()
            if getattr(self.parent_widget, 'has_vocal_track', False):
                self.parent_widget.vocal_player.pause()

    def stop(self): 
        self.media_player.stop()
        if getattr(self.parent_widget, 'has_vocal_track', False):
            self.parent_widget.vocal_player.stop()


    def seek(self, sec):
        if sec > 0.05:
            self._hide_thumbnail()
        sec = max(0.0, float(sec))
        self.current_time = sec
        self._pending_seek_sec = sec
        self.media_player.setPosition(int(sec * 1000))
        if getattr(self, 'has_vocal_track', False):
            self.vocal_player.setPosition(int(sec * 1000))

class VideoPlayerWidget(QWidget):
    frame_step_requested = pyqtSignal(int)
    scan_cut_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {config.BG2};")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(260, 260)

        self.segments: list[dict] = []
        self.current_time: float  = 0.0
        self.total_time: float    = 0.0 
        self.frame_rate: float = 30.0
        self.current_frame: int = 0
        self.frame_time_map = build_frame_time_map(0.0, self.frame_rate)
        self._last_sub: str       = ""
        self._subtitle_display_time_sec: float | None = None
        self._current_source_path: str = ""
        self._pending_seek_sec: float | None = None
        self._pending_segments: list | None = None
        self._pending_autoplay: bool = False
        self._source_ready: bool = True
        self._end_of_media_callback = None
        self._pending_thumb_path: str | None = None
        self._pending_thumb_sec: float = 0.0
        self._pending_segments: list | None = None
        self._subtitle_starts: list[float] = []
        self._subtitle_cache_idx: int = -1
        self._last_time_label_ms: int = -250
        self._last_provider_refresh_at: float = 0.0
        self._subtitle_provider = None
        self._subtitle_provider_signature = ""
        self._last_btn_state = None
        self._proxy_original_path: str = ""
        self._proxy_playback_path: str = ""
        self._source_aspect: float = 16 / 9
        self._preview_max_height: int = 720
        self._preview_max_width: int = 1280

        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)
        
        self.vocal_player = QMediaPlayer(self)
        self.vocal_audio_output = QAudioOutput(self)
        self.vocal_player.setAudioOutput(self.vocal_audio_output)
        
        self.has_vocal_track = False
        self.audio_player = self.media_player 
        self._worker = _WorkerProxy(self)

        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.media_player.mediaStatusChanged.connect(self._on_media_status_changed)

        _pretendard = "/Library/Fonts/Pretendard-Regular.ttf"
        if os.path.exists(_pretendard):
            from PyQt6.QtGui import QFontDatabase
            QFontDatabase.addApplicationFont(_pretendard)

        self._build_ui()
        self._ui_timer = QTimer()
        self._ui_timer.setInterval(int(self._get_video_ui_interval_ms()))
        self._ui_timer.timeout.connect(self._ui_tick)
        self._ui_timer.start()

        # v03.11.02: < / > frame-step hold repeat
        self._frame_step_hold_timer = QTimer(self)
        self._frame_step_hold_timer.setInterval(self._frame_step_hold_interval_ms())
        self._frame_step_hold_timer.timeout.connect(self._emit_frame_step_hold)
        self._frame_step_hold_start_timer = QTimer(self)
        self._frame_step_hold_start_timer.setSingleShot(True)
        self._frame_step_hold_start_timer.setInterval(self._frame_step_hold_delay_ms())
        self._frame_step_hold_start_timer.timeout.connect(self._activate_frame_step_hold)
        self._frame_step_hold_direction = 0
        self._frame_step_hold_active = False
        self._frame_step_hold_ignore_next_click = False


    def _on_duration_changed(self, duration):
        self.total_time = duration / 1000.0
        self._rebuild_frame_time_map()
        if duration <= 0:
            return
        self._apply_loaded_media_state()

    def _rebuild_frame_time_map(self, duration: float | None = None, fps: float | None = None):
        if fps is not None:
            self.frame_rate = normalize_fps(fps)
        if duration is not None:
            self.total_time = max(0.0, float(duration or 0.0))
        self.frame_time_map = build_frame_time_map(self.total_time, self.frame_rate)
        try:
            self.current_frame = self.frame_time_map.frame_for_sec(self.current_time)
            self.current_time = self.frame_time_map.sec_for_frame(self.current_frame)
        except Exception:
            self.current_frame = 0

    def _apply_loaded_media_state(self):
        self._source_ready = True
        if self._pending_segments is not None:
            self._set_segments(self._pending_segments)
            self._pending_segments = None
        if self._pending_seek_sec is not None:
            pending = float(self._pending_seek_sec)
            self._pending_seek_sec = None
            self.current_time = pending
            self.set_subtitle_display_time(pending, refresh=False)
            self.media_player.setPosition(int(pending * 1000))
            if getattr(self, 'has_vocal_track', False):
                self.vocal_player.setPosition(int(pending * 1000))
        if self._pending_thumb_path:
            path = self._pending_thumb_path
            sec = float(self._pending_thumb_sec)
            self._pending_thumb_path = None
            self._pending_thumb_sec = 0.0
            self._extract_and_show_thumbnail_at(path, sec)
        self._refresh_subtitle_now()
        self._notify_editor_video_ready()
        if self._pending_autoplay:
            self._pending_autoplay = False
            self.toggle_play()

    def _notify_editor_video_ready(self):
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "_position_video_expand_button"):
                QTimer.singleShot(0, parent._position_video_expand_button)
                QTimer.singleShot(250, parent._position_video_expand_button)
                return
            parent = parent.parent()

    def _on_media_status_changed(self, status):
        """EndOfMedia -> next clip callback"""
        from PyQt6.QtMultimedia import QMediaPlayer as _QMP
        if status in (_QMP.MediaStatus.LoadedMedia, _QMP.MediaStatus.BufferedMedia):
            self._apply_loaded_media_state()
        if status == _QMP.MediaStatus.EndOfMedia:
            cb = getattr(self, '_end_of_media_callback', None)
            if callable(cb):
                cb()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 8)
        layout.setSpacing(6)

        self.video_container = QWidget()
        self.video_container.setStyleSheet("background: #000000; border-radius: 4px;")
        
        self.video_stack = QStackedWidget()
        self.video_stack.setParent(self.video_container)
        
        self.video_widget = VideoSurfaceView()
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.media_player.setVideoOutput(self.video_widget.video_item)
        self.video_stack.addWidget(self.video_widget)
        
        self.thumb_label = ThumbnailLabel()
        self.video_stack.addWidget(self.thumb_label)

        self.sub_label = SubtitleLabel(self.video_container)
        self.sub_label.setVisible(False)
        self.sub_label.raise_()

        layout.addWidget(self.video_container, stretch=1)

        ctrl = QWidget()
        ctrl.setFixedHeight(48)
        ctrl.setStyleSheet("background: transparent; border: none;")
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(8)

        self.btn_scan_prev_cut = QPushButton("<<")
        self.btn_scan_prev_cut.setToolTip("이전 컷 경계까지 빠르게 탐색")
        self.btn_scan_prev_cut.setFixedWidth(42)
        self.btn_scan_prev_cut.setStyleSheet(self._control_button_style(font_size=13, padding="6px 8px"))
        self.btn_scan_prev_cut.clicked.connect(lambda: self.request_scan_cut(-1))
        ctrl_layout.addWidget(self.btn_scan_prev_cut)

        self.btn_prev_frame = QPushButton("<")
        self.btn_prev_frame.setToolTip("이전 프레임")
        self.btn_prev_frame.setFixedWidth(34)
        self.btn_prev_frame.setStyleSheet(self._control_button_style(font_size=14, padding="6px 8px"))
        self.btn_prev_frame.clicked.connect(lambda: self.request_frame_step(-1))
        ctrl_layout.addWidget(self.btn_prev_frame)

        self.btn_play = QPushButton("▶")
        self.btn_play.setToolTip("재생/일시정지 (Tab)")
        self.btn_play.setStyleSheet(self._control_button_style(font_size=12, padding="6px 12px"))
        self.btn_play.clicked.connect(self.toggle_play)
        ctrl_layout.addWidget(self.btn_play)

        self.btn_next_frame = QPushButton(">")
        self.btn_next_frame.setToolTip("다음 프레임")
        self.btn_next_frame.setFixedWidth(34)
        self.btn_next_frame.setStyleSheet(self._control_button_style(font_size=14, padding="6px 8px"))
        self.btn_next_frame.clicked.connect(lambda: self.request_frame_step(1))
        ctrl_layout.addWidget(self.btn_next_frame)

        self.btn_scan_next_cut = QPushButton(">>")
        self.btn_scan_next_cut.setToolTip("다음 컷 경계까지 빠르게 탐색")
        self.btn_scan_next_cut.setFixedWidth(42)
        self.btn_scan_next_cut.setStyleSheet(self._control_button_style(font_size=13, padding="6px 8px"))
        self.btn_scan_next_cut.clicked.connect(lambda: self.request_scan_cut(1))
        ctrl_layout.addWidget(self.btn_scan_next_cut)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #A9B0B7; font-size: 11px; font-weight: 500; background: transparent; border: none;")
        ctrl_layout.addWidget(self.time_label)

        ctrl_layout.addStretch()

        self.info_label = QLabel("영상을 불러오는 중...")
        self.info_label.setWordWrap(True)
        self.info_label.setMaximumHeight(34)
        self.info_label.setStyleSheet("color: #A9B0B7; font-size: 10px; background: transparent; border: none;")
        ctrl_layout.addWidget(self.info_label)

        layout.addWidget(ctrl)
        QTimer.singleShot(0, self._layout_video_overlay)
        QTimer.singleShot(0, self._notify_editor_video_ready)


    # ---------------------------------------------------------
    # Frame-step hold / scene guard support
    # ---------------------------------------------------------
    def _frame_step_hold_interval_ms(self) -> int:
        try:
            return max(45, int(os.environ.get("AI_SUBTITLE_FRAME_STEP_HOLD_INTERVAL_MS", "90")))
        except Exception:
            return 90

    def _frame_step_hold_delay_ms(self) -> int:
        try:
            return max(120, int(os.environ.get("AI_SUBTITLE_FRAME_STEP_HOLD_DELAY_MS", "280")))
        except Exception:
            return 280

    def _frame_step_button_clicked(self, direction: int):
        if bool(getattr(self, "_frame_step_hold_ignore_next_click", False)):
            self._frame_step_hold_ignore_next_click = False
            return
        self.request_frame_step(direction)

    def _start_frame_step_hold(self, direction: int):
        try:
            direction = 1 if int(direction) > 0 else -1
        except Exception:
            direction = 1
        self._frame_step_hold_direction = direction
        self._frame_step_hold_active = False
        self._frame_step_hold_ignore_next_click = False
        if hasattr(self, "_frame_step_hold_timer"):
            self._frame_step_hold_timer.stop()
        if hasattr(self, "_frame_step_hold_start_timer"):
            self._frame_step_hold_start_timer.start(self._frame_step_hold_delay_ms())

    def _activate_frame_step_hold(self):
        direction = int(getattr(self, "_frame_step_hold_direction", 0) or 0)
        if direction == 0:
            return
        self._frame_step_hold_active = True
        self._frame_step_hold_ignore_next_click = True
        self.request_frame_step(direction)
        if hasattr(self, "_frame_step_hold_timer"):
            self._frame_step_hold_timer.setInterval(self._frame_step_hold_interval_ms())
            self._frame_step_hold_timer.start()

    def _emit_frame_step_hold(self):
        direction = int(getattr(self, "_frame_step_hold_direction", 0) or 0)
        if direction == 0:
            self.stop_frame_step_hold()
            return
        self.request_frame_step(direction)

    def stop_frame_step_hold(self):
        if hasattr(self, "_frame_step_hold_start_timer"):
            self._frame_step_hold_start_timer.stop()
        if hasattr(self, "_frame_step_hold_timer"):
            self._frame_step_hold_timer.stop()
        self._frame_step_hold_direction = 0
        self._frame_step_hold_active = False

    def capture_frame_step_guard_image(self, max_width: int = 96, max_height: int = 54):
        try:
            widget = getattr(self, "video_widget", None) or getattr(self, "video_container", None)
            if widget is None:
                return None
            pixmap = widget.grab()
            if pixmap is None or pixmap.isNull():
                return None
            image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB32)
            if image.isNull():
                return None
            return image.scaled(
                int(max_width),
                int(max_height),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        except Exception:
            return None

    def set_scan_cut_active(self, direction: int):
        """Highlight << / >> while scan-cut is running. direction: -1, 0, 1."""
        try:
            direction = int(direction or 0)
        except Exception:
            direction = 0

        inactive = self._control_button_style(font_size=13, padding="6px 8px")
        active = (
            "QPushButton { "
            "background: #1F8F4D; color: #FFFFFF; "
            "border: 1px solid #30D158; border-radius: 6px; "
            "padding: 6px 8px; font-size: 13px; font-weight: 800; "
            "} "
            "QPushButton:hover { background: #25A85A; color: #FFFFFF; } "
            "QPushButton:pressed { background: #187A40; }"
        )

        prev_btn = getattr(self, "btn_scan_prev_cut", None)
        next_btn = getattr(self, "btn_scan_next_cut", None)

        if prev_btn is not None:
            prev_btn.setStyleSheet(active if direction < 0 else inactive)
        if next_btn is not None:
            next_btn.setStyleSheet(active if direction > 0 else inactive)

    def _control_button_style(self, *, font_size=12, padding="6px 12px") -> str:
        return f"""
            QPushButton {{
                background: #252B31; color: #F5F7FA;
                border: 1px solid #3A424A; padding: {padding}; font-weight: bold;
                border-radius: 6px; font-size: {int(font_size)}px;
            }}
            QPushButton:hover {{ background: #303841; }}
            QPushButton:pressed {{ background: #1D2329; }}
        """

    def _layout_video_overlay(self):
        if not hasattr(self, "video_container"):
            return
        rect = self.video_container.rect()
        self.video_stack.setGeometry(rect)
        video_rect = self._displayed_video_rect(rect)
        try:
            self.sub_label.setParent(self.video_container)
            self.sub_label.setGeometry(video_rect)
        except Exception:
            self.sub_label.setParent(self.video_container)
            self.sub_label.setGeometry(rect)
        self.sub_label.raise_()
        item = self._scene_subtitle_item()
        if item is not None:
            item.set_rect(QRectF(video_rect))
        try:
            self.video_widget.set_video_display_rect(QRectF(video_rect))
        except Exception:
            pass

    def _scene_subtitle_item(self):
        return getattr(getattr(self, "video_widget", None), "subtitle_item", None)

    def _set_subtitle_overlay_text(self, text: str):
        text = str(text or "")
        try:
            if self.sub_label.text() != text:
                self.sub_label.setText(text)
            self.sub_label.setVisible(False)
        except Exception:
            pass
        item = self._scene_subtitle_item()
        if item is not None:
            item.set_text(text)
        elif hasattr(self, "sub_label"):
            try:
                self.sub_label.setVisible(bool(text))
                self.sub_label.raise_()
            except Exception:
                pass

    def _set_subtitle_overlay_style(self, style: dict | None):
        try:
            self.sub_label.set_export_style(style or {})
        except Exception:
            pass
        item = self._scene_subtitle_item()
        if item is not None:
            item.set_export_style(style or {})

    def _displayed_video_rect(self, bounds):
        aspect = max(0.01, float(getattr(self, "_source_aspect", 16 / 9) or (16 / 9)))
        bw = max(1, int(bounds.width()))
        bh = max(1, int(bounds.height()))
        max_h = max(1, int(getattr(self, "_preview_max_height", 720) or 720))
        max_w = max(1, int(getattr(self, "_preview_max_width", 1280) or 1280))
        if aspect >= 1.0:
            target_w = min(bw, max_w)
            target_h = int(target_w / aspect)
            if target_h > min(bh, max_h):
                target_h = min(bh, max_h)
                target_w = int(target_h * aspect)
        else:
            target_h = min(bh, max_h)
            target_w = int(target_h * aspect)
            if target_w > min(bw, max_w):
                target_w = min(bw, max_w)
                target_h = int(target_w / aspect)
        target_w = max(1, min(bw, target_w))
        target_h = max(1, min(bh, target_h))
        x = int((bw - target_w) / 2)
        y = int((bh - target_h) / 2)
        return QRectF(x, y, target_w, target_h).toRect()

    def _source_video_rect(self, bounds):
        aspect = max(0.01, float(getattr(self, "_source_aspect", 16 / 9) or (16 / 9)))
        bw = max(1, int(bounds.width()))
        bh = max(1, int(bounds.height()))
        box_aspect = bw / max(1, bh)
        if box_aspect > aspect:
            h = bh
            w = int(h * aspect)
            x = int((bw - w) / 2)
            y = 0
        else:
            w = bw
            h = int(w / aspect)
            x = 0
            y = int((bh - h) / 2)
        return QRectF(x, y, max(1, w), max(1, h)).toRect()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_video_overlay()

    def _get_video_ui_interval_ms(self) -> int:
        try:
            settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    return max(24, min(80, int(json.load(f).get("video_ui_interval_ms", 33))))
        except Exception:
            pass
        return 33

    def _get_audio_ai_setting(self) -> str:
        """user_settings.json에서 selected_audio_ai를 읽어 반환합니다."""
        try:
            settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    return json.load(f).get("selected_audio_ai", "deepfilter")
        except Exception:
            pass
        return "deepfilter"

    def _is_video_file(self, path: str) -> bool:
        return os.path.splitext(path)[1].lower() in {
            ".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mts", ".m2ts"
        }

    def _set_media_source_if_needed(self, player, path: str):
        current = player.source().toLocalFile() if hasattr(player, "source") else ""
        if os.path.normpath(current or "") == os.path.normpath(path or ""):
            return False
        player.setSource(QUrl.fromLocalFile(path))
        return True

    def _preview_proxy_enabled(self) -> bool:
        return False

    def _proxy_path_for(self, path: str) -> str:
        return ""

    def _playback_path_for(self, path: str) -> str:
        self._proxy_original_path = path
        self._proxy_playback_path = path
        return path

    def _start_proxy_build(self, src: str, dst: str):
        return

    def _poll_proxy_build(self, src: str, tmp_dst: str, dst: str):
        return

    def _switch_to_proxy(self, proxy_path: str):
        return

    def _legacy_preview_proxy_enabled(self) -> bool:
        try:
            settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    return bool(json.load(f).get("video_preview_proxy_enabled", True))
        except Exception:
            pass
        return True


    def load(self, path, segments=None):
        self._set_segments(segments or [])
        if self._pending_segments is None:
            self._pending_segments = list(self.segments)
        if os.path.exists(path):
            self._current_source_path = path
            try:
                from core.media_info import probe_media
                info = probe_media(path)
                w = float(info.get("width", 0) or 0)
                h = float(info.get("height", 0) or 0)
                self._rebuild_frame_time_map(
                    duration=float(info.get("duration", 0.0) or self.total_time or 0.0),
                    fps=float(info.get("fps", 0.0) or self.frame_rate or 30.0),
                )
                self._source_aspect = (w / h) if w > 0 and h > 0 else (16 / 9)
            except Exception:
                self._source_aspect = 16 / 9
            playback_path = self._playback_path_for(path)
            self._pending_seek_sec = self._pending_seek_sec if self._pending_seek_sec is not None else 0.0
            source_changed = self._set_media_source_if_needed(self.media_player, playback_path)
            self._source_ready = not source_changed
            if self.has_vocal_track:
                self.vocal_player.stop()
            self.audio_output.setVolume(1.0)
            self.has_vocal_track = False
            self.info_label.setText(f"720p 표시 프리뷰 | {os.path.basename(path)}")
            if self._is_video_file(path) and self._pending_thumb_path is None:
                self._extract_and_show_thumbnail(path)
            elif not self._is_video_file(path):
                self.video_stack.setCurrentIndex(0)
            if not source_changed:
                self._apply_loaded_media_state()


    def _extract_and_show_thumbnail_at(self, path, sec=0.0):
        if not self._is_video_file(path):
            return
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            return
        self.video_stack.setCurrentIndex(1)
        temp_dir = __import__('tempfile').gettempdir()
        thumb_path = __import__('os').path.join(temp_dir, "thumb_temp_cpd.jpg")
        sec = max(0.0, float(sec))
        hh = int(sec // 3600)
        mm = int((sec % 3600) // 60)
        ss = sec % 60.0
        ts = f"{hh:02d}:{mm:02d}:{ss:06.3f}"
        cmd = ["ffmpeg", "-y", "-ss", ts, "-i", path, "-frames:v", "1", "-q:v", "2", thumb_path]
        kwargs = {'stdout': __import__('subprocess').DEVNULL, 'stderr': __import__('subprocess').DEVNULL}
        if __import__('os').name == 'nt':
            kwargs['creationflags'] = 0x08000000
        try:
            __import__('subprocess').run(cmd, check=True, timeout=3.0, **kwargs)
            if __import__('os').path.exists(thumb_path):
                pixmap = QPixmap(thumb_path)
                if not pixmap.isNull():
                    self.thumb_label.set_pixmap(pixmap)
                try:
                    __import__('os').remove(thumb_path)
                except Exception:
                    pass
        except Exception:
            pass

    def _show_thumbnail_from_cache_path(self, thumb_path: str) -> bool:
        try:
            if not thumb_path or not os.path.exists(thumb_path):
                return False
            pixmap = QPixmap(thumb_path)
            if pixmap.isNull():
                return False
            self.video_stack.setCurrentIndex(1)
            self.thumb_label.set_pixmap(pixmap)
            return True
        except Exception:
            return False

    def _thumbnail_cache_dir(self) -> str:
        try:
            owner = self.window()
            project_path = str(getattr(owner, "_current_project_path", "") or "")
        except Exception:
            project_path = ""
        return str(default_thumbnail_cache_dir(project_path))

    def show_cached_thumbnail_at(self, path: str, sec: float = 0.0, *, width: int = 640) -> bool:
        if not self._is_video_file(path):
            return False
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            return False
        result = ensure_thumbnail(
            path,
            max(0.0, float(sec or 0.0)),
            cache_dir=self._thumbnail_cache_dir(),
            width=max(160, int(width or 640)),
        )
        if result.status not in ("cached", "created") or not result.path:
            return False
        return self._show_thumbnail_from_cache_path(result.path)

    def prefetch_thumbnail_at(self, path: str, sec: float = 0.0, *, width: int = 640) -> str:
        if not self._is_video_file(path):
            return ""
        result = ensure_thumbnail(
            path,
            max(0.0, float(sec or 0.0)),
            cache_dir=self._thumbnail_cache_dir(),
            width=max(160, int(width or 640)),
        )
        if result.status in ("cached", "created"):
            return str(result.path or "")
        return ""

    def _extract_and_show_thumbnail(self, path: str):
        if not self._is_video_file(path):
            return
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            return
        self.video_stack.setCurrentIndex(1)
        temp_dir = tempfile.gettempdir()
        thumb_path = os.path.join(temp_dir, "thumb_temp_cpd.jpg")
        
        cmd = ["ffmpeg", "-y", "-ss", "00:00:00", "-i", path, "-frames:v", "1", "-q:v", "2", thumb_path]
        kwargs = {'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL}
        if os.name == 'nt': 
            kwargs['creationflags'] = 0x08000000
            
        try:
            subprocess.run(cmd, check=True, timeout=3.0, **kwargs)
            if os.path.exists(thumb_path):
                pixmap = QPixmap(thumb_path)
                if not pixmap.isNull():
                    self.thumb_label.set_pixmap(pixmap)
                try: os.remove(thumb_path)
                except: pass
        except Exception:
            pass

    def _hide_thumbnail(self):
        if self.video_stack.currentIndex() == 1:
            self.video_stack.setCurrentIndex(0)

    def _subtitle_lookup_time(self) -> float:
        override = getattr(self, "_subtitle_display_time_sec", None)
        if override is not None:
            return max(0.0, float(override))
        return max(0.0, float(getattr(self, "current_time", 0.0) or 0.0))

    def set_frame_rate(self, fps: float):
        self._rebuild_frame_time_map(fps=normalize_fps(fps))

    def snap_sec_to_frame(self, sec: float) -> float:
        frame_map = getattr(self, "frame_time_map", None)
        if frame_map is not None:
            return frame_map.snap_sec(sec)
        return snap_sec_to_frame(sec, getattr(self, "frame_rate", 30.0))

    def frame_for_sec(self, sec: float) -> int:
        return getattr(self, "frame_time_map", build_frame_time_map(self.total_time, self.frame_rate)).frame_for_sec(sec)

    def sec_for_frame(self, frame: int) -> float:
        return getattr(self, "frame_time_map", build_frame_time_map(self.total_time, self.frame_rate)).sec_for_frame(frame)

    def current_playback_frame_time(self) -> tuple[int, float]:
        frame_map = getattr(self, "frame_time_map", None)
        if frame_map is None:
            frame_map = build_frame_time_map(self.total_time, self.frame_rate)
            self.frame_time_map = frame_map
        frame = frame_map.frame_for_position_ms(self.media_player.position())
        sec = frame_map.sec_for_frame(frame)
        self.current_frame = frame
        self.current_time = sec
        return frame, sec

    def set_subtitle_display_time(self, sec: float | None, refresh: bool = True):
        if sec is None:
            self._subtitle_display_time_sec = None
        else:
            self._subtitle_display_time_sec = self.snap_sec_to_frame(sec)
        if refresh:
            self._refresh_subtitle_now()

    def _refresh_subtitle_now(self):
        cur_sub = self._find_subtitle_at(self._subtitle_lookup_time())
        if cur_sub == self._last_sub:
            return
        self._last_sub = cur_sub
        self._set_subtitle_overlay_text(cur_sub)

    def _set_segments(self, segments):
        cleaned = []
        for seg in list(segments or []):
            try:
                item = dict(seg)
                item["start"] = float(item.get("start", 0.0))
                item["end"] = float(item.get("end", 0.0))
                item["text"] = str(item.get("text", "") or "")
                cleaned.append(item)
            except Exception:
                continue
        self.segments = sorted(cleaned, key=lambda s: s["start"])
        self._subtitle_starts = [s["start"] for s in self.segments]
        self._subtitle_cache_idx = -1

    def set_subtitle_provider(self, provider):
        self._subtitle_provider = provider
        self._refresh_provider_segments(force=True)

    def apply_export_subtitle_style(self, style: dict | None):
        self._set_subtitle_overlay_style(style or {})
        self._refresh_provider_segments(force=True)
        self._refresh_subtitle_now()
        try:
            self.sub_label.update()
        except Exception:
            pass

    def _refresh_provider_segments(self, force: bool = False):
        provider = getattr(self, "_subtitle_provider", None)
        if not callable(provider):
            return
        now = time.monotonic()
        if not force and (now - float(getattr(self, "_last_provider_refresh_at", 0.0) or 0.0)) < 0.50:
            return
        self._last_provider_refresh_at = now
        try:
            segments = provider()
        except Exception:
            return
        if segments is None:
            return
        cleaned = list(segments or [])
        signature = self._segments_signature(cleaned)
        if signature and signature == getattr(self, "_subtitle_provider_signature", ""):
            return
        self._subtitle_provider_signature = signature
        self._set_segments(cleaned)
        self._refresh_subtitle_now()

    def _segments_signature(self, segments: list[dict]) -> str:
        compact = []
        for seg in segments or []:
            try:
                compact.append(
                    {
                        "start": round(float(seg.get("start", 0.0) or 0.0), 3),
                        "end": round(float(seg.get("end", 0.0) or 0.0), 3),
                        "text": str(seg.get("text", "") or ""),
                        "speaker": str(seg.get("speaker", seg.get("spk", "")) or ""),
                    }
                )
            except Exception:
                continue
        payload = json.dumps(compact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _find_subtitle_at(self, now: float) -> str:
        idx = int(getattr(self, "_subtitle_cache_idx", -1))
        if 0 <= idx < len(self.segments):
            seg = self.segments[idx]
            if seg["start"] <= now < seg["end"]:
                return seg["text"]
            if idx + 1 < len(self.segments):
                nxt = self.segments[idx + 1]
                if nxt["start"] <= now < nxt["end"]:
                    self._subtitle_cache_idx = idx + 1
                    return nxt["text"]

        idx = bisect_right(self._subtitle_starts, now) - 1
        self._subtitle_cache_idx = idx
        if 0 <= idx < len(self.segments):
            seg = self.segments[idx]
            if seg["start"] <= now < seg["end"]:
                return seg["text"]
        return ""

    def set_context_segments(self, segments: list[dict] | None = None):
        self._set_segments(segments or [])
        self._refresh_subtitle_now()

    def refresh_subtitle_context(self, segments: list[dict] | None = None):
        if segments is not None:
            self._set_segments(segments)
        self._refresh_subtitle_now()

    def load_clip_context(self, path, segments=None, seek_sec=0.0, autoplay=False, show_thumbnail=True):
        segments = list(segments or [])
        seek_sec = max(0.0, float(seek_sec))
        self._set_segments(segments)
        same_file = (os.path.normpath(getattr(self, '_current_source_path', '') or '') == os.path.normpath(path))
        if same_file:
            self.seek_direct(seek_sec)
            self._refresh_subtitle_now()
            if show_thumbnail:
                self._extract_and_show_thumbnail_at(path, seek_sec)
            if autoplay:
                self.toggle_play()
            return
        self._current_source_path = path
        self._pending_segments = segments
        self._pending_seek_sec = seek_sec
        self._pending_autoplay = bool(autoplay)
        self._pending_thumb_path = path if show_thumbnail and self._is_video_file(path) else None
        self._pending_thumb_sec = seek_sec if show_thumbnail else 0.0
        self.load(path, segments)

    def set_active_context(self, path: str, segments: list[dict] | None = None, seek_sec: float = 0.0, autoplay: bool = False, show_thumbnail: bool = True):
        self.load_clip_context(path, segments=segments, seek_sec=seek_sec, autoplay=autoplay, show_thumbnail=show_thumbnail)


    def seek_direct(self, sec):
        sec = self.snap_sec_to_frame(sec)
        self.current_time = sec
        self.current_frame = self.frame_for_sec(sec)
        self.set_subtitle_display_time(sec, refresh=False)
        self._pending_seek_sec = None
        self.media_player.setPosition(int(sec * 1000))
        if getattr(self, 'has_vocal_track', False):
            self.vocal_player.setPosition(int(sec * 1000))
        self._refresh_provider_segments(force=True)
        self._refresh_subtitle_now()

    def frame_step_seek(self, sec: float):
        """Frame-exact manual seek used by < / > and scan buttons."""
        try:
            sec = max(0.0, float(sec or 0.0))
        except Exception:
            sec = 0.0

        if self.total_time > 0.0:
            sec = min(sec, max(0.0, self.total_time))

        sec = snap_sec_to_frame(sec, self.frame_rate)
        self.current_time = sec
        try:
            self.current_frame = self.frame_time_map.frame_for_sec(sec)
        except Exception:
            self.current_frame = int(round(sec * max(1.0, float(self.frame_rate or 30.0))))

        self._pending_seek_sec = None
        self.set_subtitle_display_time(sec, refresh=False)
        self.media_player.setPosition(int(round(sec * 1000.0)))
        if getattr(self, 'has_vocal_track', False):
            self.vocal_player.setPosition(int(round(sec * 1000.0)))
        self._hide_thumbnail()
        self._refresh_subtitle_now()
        if hasattr(self, '_ui_tick'):
            self._ui_tick()

    def seek(self, sec: float):
        sec = self.snap_sec_to_frame(sec)
        if sec > 0.05:
            self._hide_thumbnail()
        self.current_time = sec
        self.current_frame = self.frame_for_sec(sec)
        self.set_subtitle_display_time(sec, refresh=False)
        self._pending_seek_sec = float(sec)
        self.media_player.setPosition(int(sec * 1000))
        if getattr(self, 'has_vocal_track', False):
            self.vocal_player.setPosition(int(sec * 1000))
        self._refresh_provider_segments(force=True)
        self._refresh_subtitle_now()


    def request_scan_cut(self, direction: int):
        try:
            direction = 1 if int(direction) > 0 else -1
        except Exception:
            direction = 1
        self.scan_cut_requested.emit(direction)

    def request_frame_step(self, direction: int):
        step = -1 if int(direction or 0) < 0 else 1
        self.pause_video()
        self.frame_step_requested.emit(step)


    def toggle_play(self):
        if not getattr(self, '_source_ready', True):
            self._pending_autoplay = True
            return
        self._hide_thumbnail()
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            if getattr(self, 'has_vocal_track', False):
                self.vocal_player.pause()
        else:
            self._refresh_provider_segments(force=True)
            if self.current_time > 0.05:
                self.media_player.setPosition(int(self.current_time * 1000))
            if getattr(self, 'has_vocal_track', False):
                self.vocal_player.setPosition(self.media_player.position())
            self.media_player.play()
            if getattr(self, 'has_vocal_track', False):
                self.vocal_player.play()
        self._update_btn()

    def pause_video(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            if getattr(self, 'has_vocal_track', False):
                self.vocal_player.pause()
            self._update_btn()

    def _update_btn(self):
        is_playing = self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        if self._last_btn_state == is_playing:
            return
        self._last_btn_state = is_playing
        self.btn_play.setText("⏸" if is_playing else "▶")

    def _ui_tick(self):
        self._update_btn()
        if not getattr(self, '_source_ready', True):
            return
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.current_playback_frame_time()
        else:
            self._refresh_provider_segments(force=False)

        def format_time(sec):
            m, s = divmod(int(sec), 60)
            return f"{m:02d}:{s:02d}"

        pos_ms = int(self.current_time * 1000)
        if abs(pos_ms - self._last_time_label_ms) >= 250:
            self._last_time_label_ms = pos_ms
            self.time_label.setText(f"{format_time(self.current_time)} / {format_time(self.total_time)}")
        
        cur_sub = self._find_subtitle_at(self._subtitle_lookup_time())

        if cur_sub != self._last_sub:
            self._last_sub = cur_sub
            self._set_subtitle_overlay_text(cur_sub)

    def closeEvent(self, event):
        if hasattr(self, '_ui_timer'): self._ui_timer.stop()
        if hasattr(self, 'media_player'): self.media_player.stop()
        if hasattr(self, 'vocal_player'): self.vocal_player.stop()
        super().closeEvent(event)
