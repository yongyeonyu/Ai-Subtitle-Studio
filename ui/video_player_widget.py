# Version: 02.02.00
# Phase: PHASE1-B
"""
ui/video_player_widget.py - PyQt6 비디오 플레이어
[v01.00.01 버그수정] _get_audio_ai_setting: 미정의 변수 'paths' 참조 오류 제거
"""
import os
import json
import subprocess
import tempfile

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QSizePolicy, QStackedWidget)
from PyQt6.QtCore import Qt, QTimer, QRectF, QUrl
from PyQt6.QtGui import QFont, QColor, QPainter, QFontMetrics, QBrush, QPainterPath, QPen, QPixmap

from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

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

class SubtitleLabel(QLabel):
    """비디오 플레이어 하단 자막 표시 위젯."""
    _FONT = QFont("Pretendard Regular", 20)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(False)

    def paintEvent(self, event):
        text = self.text()
        if not text:
            return

        # \u2028을 \n으로 치환하여 줄 나눔 처리
        text = text.replace('\u2028', '\n')

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        font = self._FONT
        painter.setFont(font)
        fm = QFontMetrics(font)

        lines  = text.split('\n')
        line_h = fm.height()
        text_w = max((fm.horizontalAdvance(ln) for ln in lines), default=0)
        text_h = line_h * len(lines) + 4 * max(0, len(lines) - 1)

        x = (self.width()  - text_w) / 2
        y = (self.height() - text_h) // 2

        painter.setPen(QColor("#FFFFFF"))
        curr_y = y
        for ln in lines:
            lx = x + (text_w - fm.horizontalAdvance(ln)) / 2
            painter.drawText(int(lx), int(curr_y + fm.ascent()), ln)
            curr_y += line_h + 4


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

    def seek(self, sec: float): 
        self.media_player.setPosition(int(sec * 1000))
        if getattr(self.parent_widget, 'has_vocal_track', False):
            self.parent_widget.vocal_player.setPosition(int(sec * 1000))


class VideoPlayerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {config.BG2};")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(400, 300)

        self.segments: list[dict] = []
        self.current_time: float  = 0.0
        self.total_time: float    = 0.0 
        self._last_sub: str       = ""

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

        _pretendard = "/Library/Fonts/Pretendard-Regular.ttf"
        if os.path.exists(_pretendard):
            from PyQt6.QtGui import QFontDatabase
            QFontDatabase.addApplicationFont(_pretendard)

        self._build_ui()
        self._ui_timer = QTimer()
        self._ui_timer.setInterval(16)
        self._ui_timer.timeout.connect(self._ui_tick)
        self._ui_timer.start()

    def _on_duration_changed(self, duration: int):
        self.total_time = duration / 1000.0

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.video_container = QWidget()
        self.video_container.setStyleSheet("background: #000000; border-radius: 4px;")
        
        vid_layout = QVBoxLayout(self.video_container)
        vid_layout.setContentsMargins(0, 0, 0, 0)
        vid_layout.setSpacing(0)

        self.video_stack = QStackedWidget()
        
        self.video_widget = QVideoWidget()
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.media_player.setVideoOutput(self.video_widget)
        self.video_stack.addWidget(self.video_widget)
        
        self.thumb_label = ThumbnailLabel()
        self.video_stack.addWidget(self.thumb_label)

        vid_layout.addWidget(self.video_stack, stretch=1) 

        self.sub_label = SubtitleLabel()
        self.sub_label.setMinimumHeight(100)
        vid_layout.addWidget(self.sub_label, stretch=0)

        layout.addWidget(self.video_container, stretch=1)

        ctrl = QWidget()
        ctrl.setFixedHeight(36)
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(12)

        self.btn_play = QPushButton("▶ 재생")
        self.btn_play.setToolTip("재생/일시정지 (Tab)")
        self.btn_play.setStyleSheet(f"""
            QPushButton {{
                background: {config.ACCENT}; color: #000000;
                border: none; padding: 6px 16px; font-weight: bold;
                border-radius: 4px; font-size: 12px;
            }}
            QPushButton:hover {{ background: {config.ACCENT_HOVER}; }}
        """)
        self.btn_play.clicked.connect(self.toggle_play)
        ctrl_layout.addWidget(self.btn_play)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet(f"color: {config.FG}; font-size: 12px; font-weight: bold;")
        ctrl_layout.addWidget(self.time_label)

        ctrl_layout.addStretch()

        self.info_label = QLabel("영상을 불러오는 중...")
        self.info_label.setStyleSheet(f"color: {config.FG2}; font-size: 11px;")
        ctrl_layout.addWidget(self.info_label)

        layout.addWidget(ctrl)

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

    def load(self, path: str, segments: list[dict] | None = None):
        self.segments = segments or []
        if os.path.exists(path):
            self.media_player.setSource(QUrl.fromLocalFile(path))
            
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
                self.info_label.setText(f"🎞️ {os.path.basename(path)}")

            self._extract_and_show_thumbnail(path)

    def _extract_and_show_thumbnail(self, path: str):
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

    def seek(self, sec: float):
        if sec > 0.05: 
            self._hide_thumbnail()
        self.current_time = sec
        self.media_player.setPosition(int(sec * 1000))
        if getattr(self, 'has_vocal_track', False):
            self.vocal_player.setPosition(int(sec * 1000))

    def toggle_play(self):
        self._hide_thumbnail() 
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            if getattr(self, 'has_vocal_track', False):
                self.vocal_player.pause()
        else:
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
        self.btn_play.setText("⏸ 정지" if is_playing else "▶ 재생")

    def _ui_tick(self):
        self._update_btn()
        self.current_time = self.media_player.position() / 1000.0

        def format_time(sec):
            m, s = divmod(int(sec), 60)
            return f"{m:02d}:{s:02d}"

        self.time_label.setText(f"{format_time(self.current_time)} / {format_time(self.total_time)}")
        
        cur_sub = ""
        for seg in self.segments:
            if seg['start'] <= self.current_time < seg['end']:
                cur_sub = seg['text']
                break

        if cur_sub != self._last_sub:
            self._last_sub = cur_sub
            self.sub_label.setText(cur_sub)

    def closeEvent(self, event):
        if hasattr(self, '_ui_timer'): self._ui_timer.stop()
        if hasattr(self, 'media_player'): self.media_player.stop()
        if hasattr(self, 'vocal_player'): self.vocal_player.stop()
        super().closeEvent(event)
