# Version: 03.13.04
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
                             QPushButton, QSizePolicy, QStackedWidget)
from PyQt6.QtCore import Qt, QTimer, QRectF, QUrl, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage

from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from core.runtime import config
from core.frame_time import build_frame_time_map, normalize_fps, snap_sec_to_frame
from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs
from core.roughcut import default_thumbnail_cache_dir, ensure_thumbnail
from core.video_codec import ffmpeg_hwdecode_args, hevc_encode_args
from ui.editor.video_playback_backend import create_video_backend
from ui.editor.video_overlay_widgets import (
    ThumbnailLabel,
    SubtitleLabel,
    SubtitleQuickOverlay,
    VideoSurfaceView,
)


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
            self.parent_widget._hide_thumbnail()
        parent = self.parent_widget
        frame = parent.frame_for_sec(max(0.0, float(sec)))
        sec = parent.sec_for_frame(frame)
        parent.current_frame = frame
        parent.current_time = sec
        parent._pending_seek_sec = sec
        pos_ms = parent.position_ms_for_frame(frame)
        self.media_player.setPosition(pos_ms)
        if getattr(parent, 'has_vocal_track', False):
            parent.vocal_player.setPosition(pos_ms)

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
        self._pending_media_source_path: str = ""
        self._media_source_loaded: bool = False
        self._source_display_name: str = ""
        self._proxy_build_proc = None
        self._proxy_build_src: str = ""
        self._proxy_build_dst: str = ""

        self.media_player = create_video_backend(self)
        self.audio_output = None

        self.vocal_player = QMediaPlayer(self)
        self.vocal_audio_output = None
        
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

    def _ensure_audio_outputs(self) -> None:
        """Create Qt audio outputs lazily to avoid startup crashes on some macOS audio setups."""
        try:
            if bool(getattr(self.media_player, "uses_qt_audio", False)) and self.audio_output is None:
                self.audio_output = QAudioOutput(self)
                self.media_player.setAudioOutput(self.audio_output)
            if self.vocal_audio_output is None:
                self.vocal_audio_output = QAudioOutput(self)
                self.vocal_player.setAudioOutput(self.vocal_audio_output)
        except Exception:
            # Keep silent fallback instead of crashing the whole app when the local
            # audio device/backend is unstable or reports unsupported channels.
            self.audio_output = None
            self.vocal_audio_output = None

    def _ensure_media_source_loaded(self) -> bool:
        path = str(getattr(self, "_pending_media_source_path", "") or "")
        if not path:
            return False
        try:
            current = self.media_player.source().toLocalFile() if hasattr(self.media_player, "source") else ""
        except Exception:
            current = ""
        if self._media_source_loaded and os.path.normpath(current or "") == os.path.normpath(path):
            return True
        source_changed = self._set_media_source_if_needed(self.media_player, path)
        self._media_source_loaded = True
        if source_changed:
            self._source_ready = False
            return False
        self._source_ready = True
        return True


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
        # Different clip sources must finish loading before we consume pending
        # seek/autoplay state, otherwise clip 2+ can start from stale time 0.
        if not self._ensure_media_source_loaded():
            return
        self._source_ready = True
        if self._pending_segments is not None:
            self._set_segments(self._pending_segments)
            self._pending_segments = None
        if self._pending_seek_sec is not None:
            pending = float(self._pending_seek_sec)
            self._pending_seek_sec = None
            pending_frame = self.frame_for_sec(pending)
            pending = self.sec_for_frame(pending_frame)
            self.current_frame = pending_frame
            self.current_time = pending
            self.set_subtitle_display_time(pending, refresh=False)
            pending_pos_ms = self.position_ms_for_frame(pending_frame)
            self.media_player.setPosition(pending_pos_ms)
            if getattr(self, 'has_vocal_track', False):
                self.vocal_player.setPosition(pending_pos_ms)
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
        
        if hasattr(self.media_player, "create_video_widget"):
            self.video_widget = self.media_player.create_video_widget()
        else:
            self.video_widget = VideoSurfaceView()
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if hasattr(self.video_widget, "video_item"):
            self.media_player.setVideoOutput(self.video_widget.video_item)
        self.video_stack.addWidget(self.video_widget)
        
        self.thumb_label = ThumbnailLabel()
        self.video_stack.addWidget(self.thumb_label)

        self.sub_label = SubtitleLabel(self.video_container)
        self.sub_label.setVisible(False)
        self.sub_label.raise_()
        self.quick_subtitle_overlay = SubtitleQuickOverlay.create(self.video_container)
        if self.quick_subtitle_overlay is not None:
            self.quick_subtitle_overlay.setVisible(False)
            self.quick_subtitle_overlay.raise_()

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

        self.source_name_label = QLabel(ctrl)
        self.source_name_label.setObjectName("VideoSourceNameLabel")
        self.source_name_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.source_name_label.setWordWrap(False)
        self.source_name_label.setMinimumWidth(0)
        self.source_name_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.source_name_label.setStyleSheet(
            "QLabel#VideoSourceNameLabel {"
            " color: #EAF2F8;"
            " background: transparent;"
            " border: none;"
            " padding: 0;"
            " font-size: 10px;"
            " font-weight: 700;"
            "}"
        )
        self.source_name_label.hide()
        ctrl_layout.addWidget(self.source_name_label)

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
        quick_overlay = getattr(self, "quick_subtitle_overlay", None)
        if quick_overlay is not None:
            try:
                quick_overlay.setParent(self.video_container)
                quick_overlay.setGeometry(video_rect)
                quick_overlay.raise_()
            except Exception:
                pass
        item = self._scene_subtitle_item()
        if item is not None:
            item.set_rect(QRectF(video_rect))
        try:
            self.video_widget.set_video_display_rect(QRectF(video_rect))
        except Exception:
            pass

    def _set_source_name_badge(self, path: str):
        name = os.path.basename(str(path or "").strip())
        self._source_display_name = name
        label = getattr(self, "source_name_label", None)
        if label is None:
            return
        label.setToolTip(name)
        if not name:
            label.hide()
            return
        self._refresh_source_name_label()

    def _refresh_source_name_label(self):
        label = getattr(self, "source_name_label", None)
        if label is None:
            return
        name = str(getattr(self, "_source_display_name", "") or "")
        if not name:
            label.hide()
            return
        label.setText(name)
        label.show()

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
        quick_overlay = getattr(self, "quick_subtitle_overlay", None)
        if quick_overlay is not None:
            quick_overlay.set_text(text)
        elif item is None and hasattr(self, "sub_label"):
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
        quick_overlay = getattr(self, "quick_subtitle_overlay", None)
        if quick_overlay is not None:
            quick_overlay.set_export_style(style or {})

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
        self._refresh_source_name_label()

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
        return self._legacy_preview_proxy_enabled()

    def _proxy_path_for(self, path: str) -> str:
        root = os.path.join(config.DATASET_DIR, "video_preview_cache")
        os.makedirs(root, exist_ok=True)
        digest = hashlib.sha1(os.path.abspath(path).encode("utf-8")).hexdigest()[:16]
        base = os.path.splitext(os.path.basename(path))[0]
        safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in base)[:48]
        return os.path.join(root, f"{safe}_{digest}_preview_720p_hevc.mp4")

    def _playback_path_for(self, path: str) -> str:
        self._proxy_original_path = path
        self._proxy_playback_path = path
        if not self._preview_proxy_enabled() or not self._is_video_file(path):
            return path
        proxy_path = self._proxy_path_for(path)
        if proxy_path and os.path.exists(proxy_path):
            self._proxy_playback_path = proxy_path
            return proxy_path
        if proxy_path:
            self._start_proxy_build(path, proxy_path)
        return path

    def _start_proxy_build(self, src: str, dst: str):
        proc = getattr(self, "_proxy_build_proc", None)
        if proc is not None and proc.poll() is None:
            return
        tmp_dst = f"{dst}.tmp.mp4"
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                os.remove(tmp_dst)
            except OSError:
                pass
            cmd = [
                ffmpeg_binary(),
                "-y",
                *ffmpeg_hwdecode_args(),
                "-i",
                src,
                "-vf",
                "scale=w=min(1280\\,iw):h=-2",
                *hevc_encode_args(quality="fast"),
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-movflags",
                "+faststart",
                tmp_dst,
            ]
            self._proxy_build_src = src
            self._proxy_build_dst = dst
            self._proxy_build_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **hidden_subprocess_kwargs(strip_qt=True),
            )
            QTimer.singleShot(500, lambda s=src, t=tmp_dst, d=dst: self._poll_proxy_build(s, t, d))
        except Exception:
            self._proxy_build_proc = None

    def _poll_proxy_build(self, src: str, _tmp_dst: str, dst: str):
        proc = getattr(self, "_proxy_build_proc", None)
        if proc is None:
            return
        if proc.poll() is None:
            QTimer.singleShot(500, lambda s=src, t=_tmp_dst, d=dst: self._poll_proxy_build(s, t, d))
            return
        ok = proc.returncode == 0 and os.path.exists(_tmp_dst)
        self._proxy_build_proc = None
        if not ok:
            try:
                os.remove(_tmp_dst)
            except OSError:
                pass
            return
        try:
            os.replace(_tmp_dst, dst)
        except OSError:
            return
        if os.path.normpath(getattr(self, "_current_source_path", "") or "") == os.path.normpath(src):
            self._switch_to_proxy(dst)

    def _switch_to_proxy(self, _proxy_path: str):
        if not _proxy_path or not os.path.exists(_proxy_path):
            return
        try:
            was_playing = self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            pos_ms = self.position_ms_for_frame(getattr(self, "current_frame", self.frame_for_sec(self.current_time)))
            self.media_player.pause()
            self.media_player.setSource(QUrl.fromLocalFile(_proxy_path))
            self.media_player.setPosition(pos_ms)
            self._pending_media_source_path = _proxy_path
            self._proxy_playback_path = _proxy_path
            self._media_source_loaded = True
            self.info_label.setText("HEVC 프리뷰")
            if was_playing:
                self.media_player.play()
        except Exception:
            pass

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
            self._set_source_name_badge(path)
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
            self._pending_media_source_path = playback_path
            self._pending_seek_sec = self._pending_seek_sec if self._pending_seek_sec is not None else 0.0
            self._media_source_loaded = False
            self._source_ready = True
            if self.has_vocal_track:
                self.vocal_player.stop()
            if self.audio_output is not None:
                self.audio_output.setVolume(1.0)
            self.has_vocal_track = False
            self.info_label.setText("")
            if self._is_video_file(path) and self._pending_thumb_path is None:
                self._extract_and_show_thumbnail(path)
            elif not self._is_video_file(path):
                self.video_stack.setCurrentIndex(0)
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
        cmd = ["ffmpeg", "-y", "-ss", ts, *ffmpeg_hwdecode_args(), "-i", path, "-frames:v", "1", "-q:v", "2", thumb_path]
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
        
        cmd = ["ffmpeg", "-y", "-ss", "00:00:00", *ffmpeg_hwdecode_args(), "-i", path, "-frames:v", "1", "-q:v", "2", thumb_path]
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

    def position_ms_for_frame(self, frame: int) -> int:
        return getattr(self, "frame_time_map", build_frame_time_map(self.total_time, self.frame_rate)).position_ms_for_frame(frame)

    def position_ms_for_sec(self, sec: float) -> int:
        return getattr(self, "frame_time_map", build_frame_time_map(self.total_time, self.frame_rate)).position_ms_for_sec(sec)

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

    def _last_playable_frame(self) -> int:
        frame_map = getattr(self, "frame_time_map", None)
        if frame_map is None:
            frame_map = build_frame_time_map(self.total_time, self.frame_rate)
            self.frame_time_map = frame_map
        if frame_map.total_frames <= 0:
            return 0
        return max(0, frame_map.total_frames - 1)

    def _last_playable_sec(self) -> float:
        return self.sec_for_frame(self._last_playable_frame())

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
        if self._media_source_loaded:
            self.media_player.setPosition(self.position_ms_for_frame(self.current_frame))
        if getattr(self, 'has_vocal_track', False) and self._media_source_loaded:
            self.vocal_player.setPosition(self.position_ms_for_frame(self.current_frame))
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
        if self._media_source_loaded:
            self.media_player.setPosition(self.position_ms_for_frame(self.current_frame))
        if getattr(self, 'has_vocal_track', False) and self._media_source_loaded:
            self.vocal_player.setPosition(self.position_ms_for_frame(self.current_frame))
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
        if self._media_source_loaded:
            self.media_player.setPosition(self.position_ms_for_frame(self.current_frame))
        if getattr(self, 'has_vocal_track', False) and self._media_source_loaded:
            self.vocal_player.setPosition(self.position_ms_for_frame(self.current_frame))
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
        self._ensure_audio_outputs()
        if not self._ensure_media_source_loaded():
            self._pending_autoplay = True
            return
        self._hide_thumbnail()
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            if getattr(self, 'has_vocal_track', False):
                self.vocal_player.pause()
        else:
            self._refresh_provider_segments(force=True)
            start_frame = self.frame_for_sec(max(0.0, float(getattr(self, "current_time", 0.0) or 0.0)))
            last_playable_frame = self._last_playable_frame()
            if self.total_time > 0.0 and start_frame >= last_playable_frame:
                start_frame = last_playable_frame
                start_sec = self.sec_for_frame(start_frame)
                self.current_frame = start_frame
                self.current_time = start_sec
                self.set_subtitle_display_time(start_sec, refresh=False)
            else:
                start_sec = self.sec_for_frame(start_frame)
            if start_sec > 0.05:
                self.media_player.setPosition(self.position_ms_for_frame(start_frame))
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
