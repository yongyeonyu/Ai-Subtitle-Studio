# Version: 03.00.26
# Phase: PHASE1-D
"""
ui/video_player_widget.py - PyQt6 비디오 플레이어
[v01.00.01 버그수정] _get_audio_ai_setting: 미정의 변수 'paths' 참조 오류 제거
"""
import os
import json
import hashlib
import shutil
import subprocess
import tempfile
import time
from bisect import bisect_right

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QSizePolicy, QStackedWidget, QComboBox,
                             QGraphicsView, QGraphicsScene)
from PyQt6.QtCore import Qt, QTimer, QRectF, QUrl, QSizeF
from PyQt6.QtGui import QFont, QColor, QPainter, QFontMetrics, QBrush, QPainterPath, QPen, QPixmap

from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem

import config

class ThumbnailLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self.setStyleSheet("background: #000000;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
    def set_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self.update() 
        
    def paintEvent(self, event):
        if self._pixmap and not self._pixmap.isNull():
            painter = QPainter(self)
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            super().paintEvent(event)


class VideoSurfaceView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.video_item = QGraphicsVideoItem()
        self.video_item.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self._scene.addItem(self.video_item)
        self.setScene(self._scene)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("background: #000000; border: none;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = QRectF(0, 0, self.viewport().width(), self.viewport().height())
        self._scene.setSceneRect(rect)
        self.video_item.setSize(QSizeF(rect.width(), rect.height()))

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
        except Exception:
            self._export_style = {}

    def setText(self, text):
        self.refresh_export_style()
        super().setText(text)

    def _qcolor(self, key, default):
        return QColor(str(self._export_style.get(key, default)))

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
            base_size = int(style.get("size", 60))
        except Exception:
            base_size = 60
        # ExportDialog renders 60px against a 1920/3840px-wide transparent strip.
        # Preview scales that proportionally to the live video widget width.
        preview_scale = max(0.35, min(1.3, self.width() / 1920.0))
        font_px = max(15, int(base_size * preview_scale))

        font = QFont(style.get("font", "Apple SD Gothic Neo"))
        font.setPixelSize(font_px)
        if style.get("bold", True):
            font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)

        lines  = text.split('\n')
        line_h = fm.height()
        text_w = max((fm.horizontalAdvance(ln) for ln in lines), default=0)
        try:
            line_spacing = int(style.get("lsp", 6) or 6)
        except Exception:
            line_spacing = 6
        lsp = max(2, int(line_spacing * preview_scale))
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
            margin = max(4, int(int(style.get("bg_margin", 18)) * preview_scale))
            radius = max(3, int(int(style.get("bg_radius", 10)) * preview_scale))
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
                sx = int(int(style.get("shdx", 3)) * preview_scale)
                sy = int(int(style.get("shdy", 3)) * preview_scale)
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
                border_w = max(0, int(int(style.get("bdr_w", 2)) * preview_scale))
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {config.BG2};")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(260, 260)

        self.segments: list[dict] = []
        self.current_time: float  = 0.0
        self.total_time: float    = 0.0 
        self._last_sub: str       = ""
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
        self._proxy_proc: subprocess.Popen | None = None
        self._proxy_original_path: str = ""
        self._proxy_playback_path: str = ""
        self._deferred_proxy_switch: str | None = None

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


    def _on_duration_changed(self, duration):
        self.total_time = duration / 1000.0
        if duration <= 0:
            return
        self._source_ready = True
        if self._pending_segments is not None:
            self._set_segments(self._pending_segments)
            self._pending_segments = None
        if self._pending_seek_sec is not None:
            pending = float(self._pending_seek_sec)
            self._pending_seek_sec = None
            self.current_time = pending
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
        if status == _QMP.MediaStatus.EndOfMedia:
            cb = getattr(self, '_end_of_media_callback', None)
            if callable(cb):
                cb()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        head = QWidget()
        head.setFixedHeight(30)
        head.setStyleSheet("background: transparent; border: none;")
        head_lay = QHBoxLayout(head)
        head_lay.setContentsMargins(0, 0, 0, 0)
        title = QLabel("미리보기")
        title.setStyleSheet("color: #F5F7FA; font-size: 12px; font-weight: 700; background: transparent; border: none;")
        head_lay.addWidget(title)
        head_lay.addStretch()
        fit = QComboBox()
        fit.addItems(["맞춤", "100%", "채움"])
        fit.setFixedWidth(78)
        fit.setStyleSheet("QComboBox { background: #202A31; color: #F5F7FA; border: 1px solid #2D3942; border-radius: 6px; padding: 4px 8px; font-size: 10px; }")
        head_lay.addWidget(fit)
        cam = QPushButton("▣")
        cam.setFixedSize(28, 26)
        cam.setStyleSheet("QPushButton { background: #202A31; color: #F5F7FA; border: 1px solid #2D3942; border-radius: 6px; }")
        head_lay.addWidget(cam)
        more = QPushButton("···")
        more.setFixedSize(34, 26)
        more.setStyleSheet("QPushButton { background: #202A31; color: #F5F7FA; border: 1px solid #2D3942; border-radius: 6px; }")
        head_lay.addWidget(more)
        layout.addWidget(head)

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

        self.sub_label = SubtitleLabel(self.video_widget.viewport())
        self.sub_label.raise_()

        layout.addWidget(self.video_container, stretch=1)

        ctrl = QWidget()
        ctrl.setFixedHeight(48)
        ctrl.setStyleSheet("background: transparent; border: none;")
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(8)

        self.btn_play = QPushButton("▶")
        self.btn_play.setToolTip("재생/일시정지 (Tab)")
        self.btn_play.setStyleSheet(f"""
            QPushButton {{
                background: #252B31; color: #F5F7FA;
                border: 1px solid #3A424A; padding: 6px 12px; font-weight: bold;
                border-radius: 6px; font-size: 12px;
            }}
            QPushButton:hover {{ background: #303841; }}
        """)
        self.btn_play.clicked.connect(self.toggle_play)
        ctrl_layout.addWidget(self.btn_play)

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

    def _layout_video_overlay(self):
        if not hasattr(self, "video_container"):
            return
        rect = self.video_container.rect()
        self.video_stack.setGeometry(rect)
        try:
            self.sub_label.setParent(self.video_widget.viewport())
            self.sub_label.setGeometry(self.video_widget.viewport().rect())
        except Exception:
            self.sub_label.setParent(self.video_container)
            self.sub_label.setGeometry(rect)
        self.sub_label.raise_()

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
        """user_settings.json에서 selected_audio_ai를 읽어 반환. 실패 시 'demucs' 기본값."""
        try:
            settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    return json.load(f).get("selected_audio_ai", "demucs")
        except Exception:
            pass
        return "demucs"

    def _is_video_file(self, path: str) -> bool:
        return os.path.splitext(path)[1].lower() in {
            ".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mts", ".m2ts"
        }

    def _preview_proxy_enabled(self) -> bool:
        try:
            settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    return bool(json.load(f).get("video_preview_proxy_enabled", True))
        except Exception:
            pass
        return True

    def _proxy_path_for(self, path: str) -> str:
        st = os.stat(path)
        key = f"{os.path.abspath(path)}|{int(st.st_mtime)}|{int(st.st_size)}"
        digest = hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()[:20]
        cache_dir = os.path.join(config.DATASET_DIR, "video_preview_cache")
        os.makedirs(cache_dir, exist_ok=True)
        return os.path.join(cache_dir, f"{digest}_preview.mp4")

    def _playback_path_for(self, path: str) -> str:
        self._proxy_original_path = path
        self._proxy_playback_path = path
        if not self._preview_proxy_enabled() or not self._is_video_file(path):
            return path
        if not shutil.which("ffmpeg"):
            return path
        try:
            proxy_path = self._proxy_path_for(path)
        except Exception:
            return path
        if os.path.exists(proxy_path) and os.path.getsize(proxy_path) > 1024:
            self._proxy_playback_path = proxy_path
            return proxy_path
        self._start_proxy_build(path, proxy_path)
        return path

    def _start_proxy_build(self, src: str, dst: str):
        if self._proxy_proc and self._proxy_proc.poll() is None:
            return
        tmp_dst = f"{dst}.tmp.mp4"
        try:
            if os.path.exists(tmp_dst):
                os.remove(tmp_dst)
        except Exception:
            pass
        cmd = [
            "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
            "-i", src,
            "-vf", "scale='min(640,iw)':-2",
            "-threads", "1",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "fastdecode",
            "-profile:v", "baseline", "-level", "3.0", "-crf", "38",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-ar", "22050",
            "-movflags", "+faststart",
            tmp_dst,
        ]
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000
        try:
            self.info_label.setText(f"저화질 프리뷰 준비 중 | {os.path.basename(src)}")
            self._proxy_proc = subprocess.Popen(cmd, **kwargs)
            self._proxy_target_tmp = tmp_dst
            self._proxy_target_final = dst
            self._proxy_timer = QTimer(self)
            self._proxy_timer.setInterval(1000)
            self._proxy_timer.timeout.connect(lambda: self._poll_proxy_build(src, tmp_dst, dst))
            self._proxy_timer.start()
        except Exception:
            self._proxy_proc = None

    def _poll_proxy_build(self, src: str, tmp_dst: str, dst: str):
        proc = getattr(self, "_proxy_proc", None)
        if proc is None or proc.poll() is None:
            return
        try:
            self._proxy_timer.stop()
        except Exception:
            pass
        ok = proc.returncode == 0 and os.path.exists(tmp_dst) and os.path.getsize(tmp_dst) > 1024
        self._proxy_proc = None
        if not ok:
            try:
                if os.path.exists(tmp_dst):
                    os.remove(tmp_dst)
            except Exception:
                pass
            return
        try:
            os.replace(tmp_dst, dst)
        except Exception:
            return
        if os.path.normpath(src) != os.path.normpath(getattr(self, "_current_source_path", "") or ""):
            return
        self._proxy_playback_path = dst
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._deferred_proxy_switch = dst
            self.info_label.setText("저화질 프리뷰 준비 완료")
            return
        self._switch_to_proxy(dst)

    def _switch_to_proxy(self, proxy_path: str):
        if not proxy_path or not os.path.exists(proxy_path):
            return
        pos = max(0, self.media_player.position())
        self.media_player.setSource(QUrl.fromLocalFile(proxy_path))
        self.media_player.setPosition(pos)
        self.info_label.setText(f"저화질 프리뷰 | {os.path.basename(self._proxy_original_path or proxy_path)}")


    def load(self, path, segments=None):
        self._set_segments(segments or [])
        if self._pending_segments is None:
            self._pending_segments = list(self.segments)
        if os.path.exists(path):
            self._current_source_path = path
            playback_path = self._playback_path_for(path)
            self._pending_seek_sec = self._pending_seek_sec if self._pending_seek_sec is not None else 0.0
            self._source_ready = False
            self.media_player.setSource(QUrl.fromLocalFile(playback_path))
            file_dir = os.path.dirname(path)
            base_name = os.path.splitext(os.path.basename(path))[0]
            vocal_path = os.path.join(file_dir, f"{base_name}_vocals.wav")
            selected_audio_ai = self._get_audio_ai_setting()
            if os.path.exists(vocal_path) and selected_audio_ai == "demucs":
                self.vocal_player.setSource(QUrl.fromLocalFile(vocal_path))
                self.audio_output.setVolume(0.0)
                self.vocal_audio_output.setVolume(1.0)
                self.has_vocal_track = True
                self.info_label.setText(f"🎙️ AI 보컬 모드 | {os.path.basename(path)}")
            else:
                self.audio_output.setVolume(1.0)
                self.has_vocal_track = False
                prefix = "저화질 프리뷰" if os.path.normpath(playback_path) != os.path.normpath(path) else "원본 프리뷰"
                self.info_label.setText(f"{prefix} | {os.path.basename(path)}")
            if self._pending_thumb_path is None:
                self._extract_and_show_thumbnail(path)


    def _extract_and_show_thumbnail_at(self, path, sec=0.0):
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

    def _extract_and_show_thumbnail(self, path: str):
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

    def _refresh_subtitle_now(self):
        cur_sub = self._find_subtitle_at(float(getattr(self, 'current_time', 0.0) or 0.0))
        self._last_sub = cur_sub
        try:
            self.sub_label.setText(cur_sub)
            self.sub_label.setVisible(bool(cur_sub))
            self.sub_label.raise_()
        except Exception:
            pass

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
        self._pending_thumb_path = path if show_thumbnail else None
        self._pending_thumb_sec = seek_sec if show_thumbnail else 0.0
        self.load(path, segments)

    def set_active_context(self, path: str, segments: list[dict] | None = None, seek_sec: float = 0.0, autoplay: bool = False, show_thumbnail: bool = True):
        self.load_clip_context(path, segments=segments, seek_sec=seek_sec, autoplay=autoplay, show_thumbnail=show_thumbnail)


    def seek_direct(self, sec):
        sec = max(0.0, float(sec))
        self.current_time = sec
        self._pending_seek_sec = None
        self.media_player.setPosition(int(sec * 1000))
        if getattr(self, 'has_vocal_track', False):
            self.vocal_player.setPosition(int(sec * 1000))
        self._refresh_subtitle_now()

    def seek(self, sec: float):
        if sec > 0.05:
            self._hide_thumbnail()
        self.current_time = sec
        self._pending_seek_sec = float(sec)
        self.media_player.setPosition(int(sec * 1000))
        if getattr(self, 'has_vocal_track', False):
            self.vocal_player.setPosition(int(sec * 1000))
        self._refresh_subtitle_now()


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
            if self._deferred_proxy_switch:
                proxy_path = self._deferred_proxy_switch
                self._deferred_proxy_switch = None
                self._switch_to_proxy(proxy_path)
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
            self.current_time = self.media_player.position() / 1000.0
            self._refresh_provider_segments(force=False)

        def format_time(sec):
            m, s = divmod(int(sec), 60)
            return f"{m:02d}:{s:02d}"

        pos_ms = int(self.current_time * 1000)
        if abs(pos_ms - self._last_time_label_ms) >= 250:
            self._last_time_label_ms = pos_ms
            self.time_label.setText(f"{format_time(self.current_time)} / {format_time(self.total_time)}")
        
        cur_sub = self._find_subtitle_at(float(self.current_time))

        if cur_sub != self._last_sub:
            self._last_sub = cur_sub
            self.sub_label.setText(cur_sub)
            self.sub_label.setVisible(bool(cur_sub))
            self.sub_label.raise_()

    def closeEvent(self, event):
        if hasattr(self, '_ui_timer'): self._ui_timer.stop()
        if hasattr(self, 'media_player'): self.media_player.stop()
        if hasattr(self, 'vocal_player'): self.vocal_player.stop()
        super().closeEvent(event)
