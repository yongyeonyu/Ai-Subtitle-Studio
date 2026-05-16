# Version: 03.13.04
# Phase: PHASE2
"""
ui/video_player_widget.py - PyQt6 비디오 플레이어
[v01.00.01 버그수정] _get_audio_ai_setting: 미정의 변수 'paths' 참조 오류 제거
"""
import os
import json
import subprocess
import tempfile
import time
import threading

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QSizePolicy, QStackedWidget)
from PyQt6.QtCore import Qt, QTimer, QUrl, QEvent, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QColor

from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from core.runtime import config
from core.frame_time import build_frame_time_map, normalize_fps, sec_to_floor_frame, snap_sec_to_frame
from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs
from core.roughcut import default_thumbnail_cache_dir, ensure_thumbnail, thumbnail_cache_path
from core.video_preview_proxy import preview_proxy_path_for, register_preview_proxy_created
from core.video_codec import ffmpeg_hwdecode_args, hevc_encode_args
from ui.editor.video_playback_backend import create_video_backend
from ui.editor.video_player_overlay_mixin import VideoPlayerOverlayMixin
from ui.editor.video_player_subtitles import VideoPlayerSubtitleMixin
from ui.editor.video_overlay_widgets import (
    ThumbnailLabel,
    SubtitleLabel,
    SubtitleQuickOverlay,
    VideoSurfaceView,
)
from ui.gpu_rendering import scenegraph_enabled


class _MirrorLabel(QLabel):
    text_changed = pyqtSignal(str)
    visible_changed = pyqtSignal(bool)

    def setText(self, text):
        next_text = str(text or "")
        if next_text == self.text():
            super().setText(next_text)
            return
        super().setText(next_text)
        self.text_changed.emit(next_text)

    def setVisible(self, visible):
        changed = bool(visible) != self.isVisible()
        super().setVisible(visible)
        if changed:
            self.visible_changed.emit(bool(visible))


class _DormantAuxPlayer:
    backend_name = "dormant"
    uses_qt_audio = False
    PlaybackState = QMediaPlayer.PlaybackState
    MediaStatus = QMediaPlayer.MediaStatus

    def source(self):
        return QUrl()

    def playbackState(self):
        return QMediaPlayer.PlaybackState.PausedState

    def position(self):
        return 0

    def play(self):
        return

    def pause(self):
        return

    def stop(self):
        return

    def setPosition(self, _position_ms):
        return

    def setAudioOutput(self, _output):
        return

    def setVideoOutput(self, _output):
        return

    def setSource(self, _source=None):
        return


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
            self.parent_widget._video_surface_primed = True
            self.media_player.play()
            if getattr(self.parent_widget, 'has_vocal_track', False):
                vocal_player = self.parent_widget._ensure_vocal_player()
                vocal_player.setPosition(self.media_player.position())
                vocal_player.play()
        else: 
            self.media_player.pause()
            if getattr(self.parent_widget, 'has_vocal_track', False):
                self.parent_widget._ensure_vocal_player().pause()

    def stop(self): 
        self.media_player.stop()
        if getattr(self.parent_widget, 'has_vocal_track', False):
            self.parent_widget._ensure_vocal_player().stop()


    def seek(self, sec):
        parent = self.parent_widget
        parent._apply_seek_state(
            sec,
            remember_pending=True,
            hide_thumbnail_threshold=0.05,
            refresh_provider=False,
            refresh_subtitle=False,
        )

class VideoPlayerWidget(VideoPlayerOverlayMixin, VideoPlayerSubtitleMixin, QWidget):
    frame_step_requested = pyqtSignal(int)
    scan_cut_requested = pyqtSignal(int)
    initial_thumbnail_ready = pyqtSignal(str, str)

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
        self._subtitle_starts: list[float] = []
        self._subtitle_ends: list[float] = []
        self._subtitle_texts: list[str] = []
        self._subtitle_count: int = 0
        self._subtitle_cache_idx: int = -1
        self._last_time_label_ms: int = -250
        self._last_frame_count_text: str = ""
        self._last_provider_refresh_at: float = 0.0
        self._subtitle_provider = None
        self._subtitle_provider_signature = ""
        self._subtitle_provider_segments_ref = None
        self._context_segments_ref = None
        self._context_segments_signature = ""
        self._last_btn_state = None
        self._proxy_original_path: str = ""
        self._proxy_playback_path: str = ""
        self._source_aspect: float = 16 / 9
        self._display_aspect: float = 16 / 9
        self._source_width: int = 0
        self._source_height: int = 0
        self._preview_max_height: int = 720
        self._preview_max_width: int = 1280
        self._pending_media_source_path: str = ""
        self._media_source_loaded: bool = False
        self._video_surface_primed: bool = False
        self._last_unprimed_thumbnail_at: float = 0.0
        self._last_unprimed_thumbnail_sec: float | None = None
        self._source_display_name: str = ""
        self._source_media_info: dict[str, object] = {}
        self._source_info_status_text: str = "영상 정보를 불러오는 중..."
        self._source_preview_label: str = ""
        self._initial_thumbnail_request_key: str = ""
        self._proxy_build_proc = None
        self._proxy_build_src: str = ""
        self._proxy_build_dst: str = ""
        self._scan_cut_active_direction: int = 0
        self._shutdown_in_progress = False

        self.media_player = create_video_backend(self)
        self.audio_output = None

        self.vocal_player = _DormantAuxPlayer()
        self.vocal_audio_output = None
        
        self.has_vocal_track = False
        self.audio_player = self.media_player 
        self._worker = _WorkerProxy(self)

        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.media_player.mediaStatusChanged.connect(self._on_media_status_changed)
        try:
            self.media_player.playbackStateChanged.connect(self._on_playback_state_changed)
        except Exception:
            pass
        self.initial_thumbnail_ready.connect(self._on_initial_thumbnail_ready)

        _pretendard = "/Library/Fonts/Pretendard-Regular.ttf"
        if os.path.exists(_pretendard):
            from PyQt6.QtGui import QFontDatabase
            QFontDatabase.addApplicationFont(_pretendard)

        self._build_ui()
        self._provider_refresh_requested = False
        self._ui_timer = QTimer(self)
        self._play_ui_interval_ms = int(self._get_video_ui_interval_ms())
        self._idle_ui_interval_ms = max(90, int(self._play_ui_interval_ms * 3))
        self._ui_timer.setInterval(self._idle_ui_interval_ms)
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
            if self.has_vocal_track and self.vocal_audio_output is None:
                vocal_player = self._ensure_vocal_player()
                self.vocal_audio_output = QAudioOutput(self)
                vocal_player.setAudioOutput(self.vocal_audio_output)
        except Exception:
            # Keep silent fallback instead of crashing the whole app when the local
            # audio device/backend is unstable or reports unsupported channels.
            self.audio_output = None
            self.vocal_audio_output = None

    def _ensure_vocal_player(self) -> QMediaPlayer:
        player = getattr(self, "vocal_player", None)
        if isinstance(player, QMediaPlayer):
            return player
        player = QMediaPlayer(self)
        self.vocal_player = player
        if self.vocal_audio_output is not None:
            try:
                player.setAudioOutput(self.vocal_audio_output)
            except Exception:
                pass
        return player

    def _release_vocal_player(self) -> None:
        player = getattr(self, "vocal_player", None)
        if isinstance(player, QMediaPlayer):
            try:
                player.stop()
            except Exception:
                pass
            try:
                player.setAudioOutput(None)
            except Exception:
                pass
            try:
                player.setSource(QUrl())
            except Exception:
                pass
            try:
                player.deleteLater()
            except Exception:
                pass
        self.vocal_player = _DormantAuxPlayer()
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
            self._video_surface_primed = False
            self._source_ready = False
            return False
        self._source_ready = True
        return True


    def _on_duration_changed(self, duration):
        if duration <= 0:
            # Some backends emit a transient zero duration while swapping from
            # the original 4K file to the generated 720p proxy. Keep the probed
            # media duration so the control bar does not fall back to 00:00/00:00.
            return
        self.total_time = duration / 1000.0
        self._rebuild_frame_time_map()
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
        self._update_frame_count_label(force=True)

    def _apply_loaded_media_state(self):
        # Different clip sources must finish loading before we consume pending
        # seek/autoplay state, otherwise clip 2+ can start from stale time 0.
        if not self._ensure_media_source_loaded():
            return
        self._media_source_loaded = True
        self._source_ready = True
        if self._pending_segments is not None:
            self._set_segments(self._pending_segments)
            self._pending_segments = None
        if self._pending_seek_sec is not None:
            pending = float(self._pending_seek_sec)
            self._pending_seek_sec = None
            self._apply_seek_state(
                pending,
                remember_pending=False,
                refresh_provider=False,
                refresh_subtitle=False,
            )
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

    def _on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._video_surface_primed = True
            self._hide_thumbnail()
        self._update_btn()

    def _create_transport_button(
        self,
        text: str,
        *,
        tooltip: str,
        width: int | None = None,
        font_size: int = 12,
        padding: str = "6px 12px",
        callback=None,
    ) -> QPushButton:
        button = QPushButton(text)
        button.setToolTip(tooltip)
        if width is not None:
            button.setFixedWidth(int(width))
        button.setStyleSheet(self._control_button_style(font_size=font_size, padding=padding))
        if callable(callback):
            button.clicked.connect(callback)
        return button

    def _fallback_to_qt_video_backend(self, reason: Exception | str):
        try:
            from core.runtime.logger import get_logger

            get_logger().log(f"  ⚠️ [비디오] mpv 미리보기 초기화 실패 → Qt 백엔드로 전환: {reason}")
        except Exception:
            pass
        old_player = getattr(self, "media_player", None)
        try:
            if old_player is not None and hasattr(old_player, "stop"):
                old_player.stop()
        except Exception:
            pass
        try:
            if old_player is not None and hasattr(old_player, "deleteLater"):
                old_player.deleteLater()
        except Exception:
            pass
        player = QMediaPlayer(self)
        player.backend_name = "qt"  # type: ignore[attr-defined]
        player.uses_qt_audio = True  # type: ignore[attr-defined]
        self.media_player = player
        self.audio_player = player
        self.audio_output = None
        try:
            self._worker.media_player = player
        except Exception:
            pass
        player.durationChanged.connect(self._on_duration_changed)
        player.mediaStatusChanged.connect(self._on_media_status_changed)
        try:
            player.playbackStateChanged.connect(self._on_playback_state_changed)
        except Exception:
            pass
        return player

    def _build_video_surface_stack(self) -> None:
        self.video_container = QWidget()
        self.video_container.setStyleSheet("background: #000000; border-radius: 4px;")

        self.video_stack = QStackedWidget()
        self.video_stack.setParent(self.video_container)

        if hasattr(self.media_player, "create_video_widget"):
            try:
                self.video_widget = self.media_player.create_video_widget()
            except Exception as exc:
                self._fallback_to_qt_video_backend(exc)
                self.video_widget = VideoSurfaceView()
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

    def _play_pause_tooltip_text(self) -> str:
        return (
            "재생/일시정지\n"
            "Tab: 기본\n"
            "Shift: 자막 에디터\n"
            "Space: 캔버스\n"
            "반복재생 체크 시 선택 세그먼트만 반복\n"
            "캔버스 Space 두 번: 다음 세그먼트"
        )

    def _build_control_bar(self) -> QWidget:
        ctrl = QWidget()
        ctrl.setFixedHeight(48)
        ctrl.setStyleSheet("background: transparent; border: none;")
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(8)

        self.btn_scan_prev_cut = self._create_transport_button(
            "<<",
            tooltip="이전 컷 경계까지 빠르게 탐색",
            width=42,
            font_size=13,
            padding="6px 8px",
            callback=lambda: self.request_scan_cut(-1),
        )
        ctrl_layout.addWidget(self.btn_scan_prev_cut)

        self.btn_prev_frame = self._create_transport_button(
            "<",
            tooltip="이전 프레임",
            width=34,
            font_size=14,
            padding="6px 8px",
            callback=lambda: self.request_frame_step(-1),
        )
        ctrl_layout.addWidget(self.btn_prev_frame)

        self.btn_play = self._create_transport_button(
            "▶",
            tooltip=self._play_pause_tooltip_text(),
            callback=self.toggle_play,
        )
        ctrl_layout.addWidget(self.btn_play)

        self.btn_next_frame = self._create_transport_button(
            ">",
            tooltip="다음 프레임",
            width=34,
            font_size=14,
            padding="6px 8px",
            callback=lambda: self.request_frame_step(1),
        )
        ctrl_layout.addWidget(self.btn_next_frame)

        self.btn_scan_next_cut = self._create_transport_button(
            ">>",
            tooltip="다음 컷 경계까지 빠르게 탐색",
            width=42,
            font_size=13,
            padding="6px 8px",
            callback=lambda: self.request_scan_cut(1),
        )
        ctrl_layout.addWidget(self.btn_scan_next_cut)

        self.time_label = _MirrorLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #A9B0B7; font-size: 11px; font-weight: 500; background: transparent; border: none;")
        ctrl_layout.addWidget(self.time_label)

        self.frame_count_label = _MirrorLabel("F 0 / 0")
        self.frame_count_label.setObjectName("VideoFrameCountLabel")
        self.frame_count_label.setToolTip("현재 프레임 / 전체 프레임")
        self.frame_count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.frame_count_label.setWordWrap(False)
        self.frame_count_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.frame_count_label.setStyleSheet(
            "QLabel#VideoFrameCountLabel {"
            " color: #8FE7FF;"
            " background: transparent;"
            " border: none;"
            " padding: 0 4px;"
            " font-size: 10px;"
            " font-weight: 800;"
            "}"
        )
        ctrl_layout.addWidget(self.frame_count_label)

        ctrl_layout.addSpacing(12)

        self.status_info_container = QWidget(ctrl)
        self.status_info_container.setObjectName("VideoStatusInfoContainer")
        self.status_info_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.status_info_container.setFixedHeight(32)
        status_layout = QHBoxLayout(self.status_info_container)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(6)

        self.info_label = _MirrorLabel("영상 정보를 불러오는 중...")
        self.info_label.setObjectName("VideoSourceMetaLabel")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.info_label.setWordWrap(False)
        self.info_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.info_label.setMinimumHeight(32)
        self.info_label.setStyleSheet(
            "QLabel#VideoSourceMetaLabel {"
            " color: #A9B0B7;"
            " background: #1A2127;"
            " border: 1px solid #2D3942;"
            " border-radius: 9px;"
            " padding: 0 12px;"
            " font-size: 10px;"
            "}"
        )
        status_layout.addWidget(self.info_label, 1)

        self.source_name_label = _MirrorLabel("")
        self.source_name_label.setObjectName("VideoSourceNameLabel")
        self.source_name_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.source_name_label.setWordWrap(False)
        self.source_name_label.setMinimumWidth(0)
        self.source_name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.source_name_label.setMinimumHeight(32)
        self.source_name_label.setStyleSheet(
            "QLabel#VideoSourceNameLabel {"
            " color: #EAF2F8;"
            " background: #182126;"
            " border: 1px solid #2F4852;"
            " border-radius: 9px;"
            " padding: 0 12px;"
            " font-size: 10px;"
            " font-weight: 700;"
            "}"
        )
        status_layout.addWidget(self.source_name_label, 1)

        ctrl_layout.addWidget(self.status_info_container, 1)
        return ctrl

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 8)
        layout.setSpacing(6)
        self._build_video_surface_stack()

        layout.addWidget(self.video_container, stretch=1)
        ctrl = self._build_control_bar()
        self._control_bar_widget = ctrl
        self._control_bar_widget.installEventFilter(self)
        for label in (self.time_label, self.info_label, self.frame_count_label, self.source_name_label):
            label.text_changed.connect(self._sync_quick_control_bar)
            label.visible_changed.connect(self._sync_quick_control_bar)
        self._quick_control_bar = self._create_quick_control_bar(ctrl)
        self._refresh_source_info_label()
        self._refresh_source_name_label()
        self._sync_quick_control_bar()

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
        self._scan_cut_active_direction = direction

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
        self._sync_quick_control_bar()

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

    def _format_probe_fps(self, fps_value) -> str:
        try:
            fps = float(fps_value or 0.0)
        except Exception:
            fps = 0.0
        if fps <= 0.0:
            return ""
        return f"{fps:.2f}".rstrip("0").rstrip(".") + "fps"

    def _format_probe_bitrate(self, bit_rate_value) -> str:
        try:
            bit_rate = int(bit_rate_value or 0)
        except Exception:
            bit_rate = 0
        if bit_rate <= 0:
            return ""
        if bit_rate >= 1_000_000:
            return f"{bit_rate / 1_000_000.0:.1f}".rstrip("0").rstrip(".") + "Mbps"
        if bit_rate >= 1_000:
            return f"{bit_rate / 1_000.0:.0f}kbps"
        return f"{bit_rate}bps"

    def _format_probe_color_info(self, info: dict | None) -> str:
        info = dict(info or {})
        pix_fmt = str(info.get("pix_fmt", "") or "").strip()
        primaries = str(info.get("color_primaries", "") or "").strip()
        color_space = str(info.get("color_space", "") or "").strip()
        transfer = str(info.get("color_transfer", "") or "").strip()
        tokens: list[str] = []
        if pix_fmt:
            tokens.append(pix_fmt)
        for value in (primaries, color_space, transfer):
            if value and value not in tokens:
                tokens.append(value)
            if len(tokens) >= 3:
                break
        if not tokens:
            return ""
        return " ".join(tokens)

    def _format_source_media_summary(self) -> str:
        info = dict(getattr(self, "_source_media_info", {}) or {})
        parts: list[str] = []
        preview_label = str(getattr(self, "_source_preview_label", "") or "").strip()
        if preview_label:
            parts.append(preview_label)
        width = int(info.get("width", 0) or 0)
        height = int(info.get("height", 0) or 0)
        if width > 0 and height > 0:
            parts.append(f"{width}x{height}")
        fps_text = self._format_probe_fps(info.get("fps", 0.0))
        if fps_text:
            parts.append(fps_text)
        color_text = self._format_probe_color_info(info)
        if color_text:
            parts.append(color_text)
        bitrate_text = self._format_probe_bitrate(info.get("bit_rate", 0))
        if bitrate_text:
            parts.append(bitrate_text)
        return " | ".join(part for part in parts if part)

    def _refresh_source_info_label(self):
        label = getattr(self, "info_label", None)
        if label is None:
            return
        status_text = str(getattr(self, "_source_info_status_text", "") or "").strip()
        summary_text = self._format_source_media_summary()
        text = status_text or summary_text
        label.setText(text)
        label.setToolTip(text)

    def _set_source_info_status(self, text: str):
        self._source_info_status_text = str(text or "")
        self._refresh_source_info_label()

    def apply_source_media_probe(self, path: str, info: dict | None):
        current_path = str(getattr(self, "_current_source_path", "") or "")
        target_path = str(path or "")
        try:
            if current_path and target_path and os.path.normpath(current_path) != os.path.normpath(target_path):
                return
        except Exception:
            if current_path and target_path and current_path != target_path:
                return
        probe_info = dict(info or {})
        self._source_media_info = probe_info
        width = int(probe_info.get("width", 0) or 0)
        height = int(probe_info.get("height", 0) or 0)
        self._source_width = width
        self._source_height = height
        if width > 0 and height > 0:
            self._source_aspect = width / height
        duration = float(probe_info.get("duration", 0.0) or 0.0)
        fps = float(probe_info.get("fps", 0.0) or 0.0)
        if duration > 0.0 or fps > 0.0:
            self._rebuild_frame_time_map(
                duration=duration or self.total_time or 0.0,
                fps=fps or self.frame_rate or 30.0,
            )
        if self._source_info_status_text in {"", "영상 정보를 불러오는 중...", "영상을 불러오는 중..."}:
            self._source_info_status_text = ""
        self._refresh_source_info_label()

    def _set_source_name_badge(self, path: str):
        name = os.path.basename(str(path or "").strip())
        self._source_display_name = name
        label = getattr(self, "source_name_label", None)
        if label is None:
            return
        label.setToolTip(name)
        self._refresh_source_name_label()

    def _refresh_source_name_label(self):
        label = getattr(self, "source_name_label", None)
        if label is None:
            return
        name = str(getattr(self, "_source_display_name", "") or "")
        label.setText(name)
        label.setToolTip(name)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_video_overlay()
        self._refresh_source_name_label()
        self._sync_quick_control_bar()

    def eventFilter(self, obj, event):
        if obj is getattr(self, "_control_bar_widget", None) and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            quick = getattr(self, "_quick_control_bar", None)
            if quick is not None:
                quick.setGeometry(obj.rect())
                quick.raise_()
        return super().eventFilter(obj, event)

    def _create_quick_control_bar(self, parent):
        if not scenegraph_enabled("video"):
            return None
        qml_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "qml", "video_control_bar.qml"))
        if not os.path.exists(qml_path):
            return None
        try:
            from PyQt6.QtQuickWidgets import QQuickWidget
        except Exception:
            return None
        try:
            quick = QQuickWidget(parent)
            quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
            quick.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            quick.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            quick.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            quick.setClearColor(QColor(0, 0, 0, 0))
            quick.setSource(QUrl.fromLocalFile(qml_path))
            if quick.status() == QQuickWidget.Status.Error:
                quick.deleteLater()
                return None
            root = quick.rootObject()
            if root is not None:
                root.playRequested.connect(self.toggle_play)
                root.prevFrameRequested.connect(lambda: self.request_frame_step(-1))
                root.nextFrameRequested.connect(lambda: self.request_frame_step(1))
                root.prevScanRequested.connect(lambda: self.request_scan_cut(-1))
                root.nextScanRequested.connect(lambda: self.request_scan_cut(1))
            quick.setGeometry(parent.rect())
            quick.show()
            quick.raise_()
            return quick
        except Exception:
            return None

    def _quick_control_bar_state(self) -> dict:
        return {
            "timeText": str(getattr(self.time_label, "text", lambda: "")() or ""),
            "infoText": str(getattr(self.info_label, "text", lambda: "")() or ""),
            "frameText": str(getattr(self.frame_count_label, "text", lambda: "")() or ""),
            "sourceNameText": (
                str(getattr(self.source_name_label, "text", lambda: "")() or "")
                if not bool(getattr(self.source_name_label, "isHidden", lambda: True)())
                else ""
            ),
            "playText": str(getattr(self.btn_play, "text", lambda: "▶")() or "▶"),
            "playing": bool(self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState),
            "scanPrevActive": bool(getattr(self, "_scan_cut_active_direction", 0) < 0),
            "scanNextActive": bool(getattr(self, "_scan_cut_active_direction", 0) > 0),
        }

    def _sync_quick_control_bar(self, *_args):
        quick = getattr(self, "_quick_control_bar", None)
        if quick is None:
            return
        try:
            root = quick.rootObject()
            if root is None:
                return
            state = self._quick_control_bar_state()
            for key, value in state.items():
                root.setProperty(key, value)
        except Exception:
            pass

    def _get_video_ui_interval_ms(self) -> int:
        try:
            settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    return max(24, min(80, int(json.load(f).get("video_ui_interval_ms", 50))))
        except Exception:
            pass
        return 50

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
        backend_name = str(getattr(getattr(self, "media_player", None), "backend_name", "") or "").strip().lower()
        default_enabled = backend_name not in {"mpv", "vlc"}
        return self._legacy_preview_proxy_enabled(default=default_enabled)

    def _proxy_path_for(self, path: str) -> str:
        return preview_proxy_path_for(path)

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
            if self._source_needs_preview_proxy() and self._wait_for_preview_proxy_enabled():
                self._proxy_playback_path = ""
                self._source_ready = False
                try:
                    self._set_source_info_status("720p 프리뷰 생성 중...")
                except Exception:
                    pass
                return ""
            if self._source_needs_preview_proxy():
                try:
                    self._set_source_info_status("720p 프리뷰 준비 중")
                except Exception:
                    pass
        return path

    def _source_needs_preview_proxy(self) -> bool:
        try:
            width = int(getattr(self, "_source_width", 0) or 0)
            height = int(getattr(self, "_source_height", 0) or 0)
            return bool(width > int(getattr(self, "_preview_max_width", 1280) or 1280) or height > int(getattr(self, "_preview_max_height", 720) or 720))
        except Exception:
            return False

    def _wait_for_preview_proxy_enabled(self) -> bool:
        env_value = str(os.environ.get("AI_SUBTITLE_VIDEO_PREVIEW_WAIT", "") or "").strip().lower()
        if env_value in {"1", "true", "yes", "on"}:
            return True
        if env_value in {"0", "false", "no", "off"}:
            return False
        try:
            settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "video_preview_proxy_wait_for_build" in data:
                    value = data.get("video_preview_proxy_wait_for_build")
                    if isinstance(value, str):
                        value = value.strip().lower()
                        if value in {"1", "true", "yes", "on"}:
                            return True
                        if value in {"0", "false", "no", "off"}:
                            return False
                    return bool(value)
        except Exception:
            pass
        # Keep the real media loaded immediately. Waiting for the proxy leaves
        # the preview at a thumbnail-only 00:00/00:00 state on long 4K clips.
        return False

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
                "scale=w=min(1280\\,iw):h=min(720\\,ih):force_original_aspect_ratio=decrease:force_divisible_by=2",
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
        try:
            register_preview_proxy_created(dst)
        except Exception:
            pass
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
            self._source_ready = True
            self._source_preview_label = "HEVC 프리뷰"
            self._set_source_info_status("")
            pending_autoplay = bool(getattr(self, "_pending_autoplay", False))
            self._video_surface_primed = bool(was_playing or pending_autoplay)
            self._pending_autoplay = False
            if was_playing or pending_autoplay:
                self.media_player.play()
        except Exception:
            pass

    def _legacy_preview_proxy_enabled(self, *, default: bool = True) -> bool:
        env_value = str(os.environ.get("AI_SUBTITLE_VIDEO_PREVIEW_PROXY", "") or "").strip().lower()
        if env_value in {"1", "true", "yes", "on"}:
            return True
        if env_value in {"0", "false", "no", "off"}:
            return False
        try:
            settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "video_preview_proxy_enabled" in data:
                    value = data.get("video_preview_proxy_enabled")
                    if isinstance(value, str):
                        value = value.strip().lower()
                        if value in {"1", "true", "yes", "on"}:
                            return True
                        if value in {"0", "false", "no", "off"}:
                            return False
                    return bool(value)
        except Exception:
            pass
        return bool(default)


    def load(self, path, segments=None, *, defer_probe: bool = False):
        self._set_segments(segments or [])
        if self._pending_segments is None:
            self._pending_segments = list(self.segments)
        self._initial_thumbnail_request_key = ""
        if os.path.exists(path):
            self._set_source_name_badge(path)
            self._current_source_path = path
            self._source_media_info = {}
            self._source_preview_label = ""
            self._set_source_info_status("영상 정보를 불러오는 중..." if defer_probe else "영상을 불러오는 중...")
            self._video_surface_primed = False
            if not defer_probe:
                try:
                    from core.media_info import probe_media
                    info = probe_media(path)
                    self.apply_source_media_probe(path, info)
                except Exception:
                    self._source_aspect = 16 / 9
                    self._source_width = 0
                    self._source_height = 0
            playback_path = self._playback_path_for(path)
            self._pending_media_source_path = playback_path
            self._pending_seek_sec = self._pending_seek_sec if self._pending_seek_sec is not None else 0.0
            self._media_source_loaded = False
            self._source_ready = bool(playback_path)
            if self.has_vocal_track or isinstance(getattr(self, "vocal_player", None), QMediaPlayer):
                self._release_vocal_player()
            if self.audio_output is not None:
                self.audio_output.setVolume(1.0)
            self.has_vocal_track = False
            if playback_path:
                if not defer_probe:
                    self._set_source_info_status("")
            if self._is_video_file(path) and self._pending_thumb_path is None:
                if defer_probe:
                    self._schedule_initial_thumbnail_prepare(path, 0.0, width=640)
                else:
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

    def _thumbnail_request_key(self, path: str, sec: float = 0.0, *, width: int = 640) -> str:
        try:
            normalized = os.path.normpath(str(path or ""))
        except Exception:
            normalized = str(path or "")
        return f"{normalized}|{float(sec or 0.0):.3f}|{int(width or 640)}"

    def _cached_thumbnail_path(self, path: str, sec: float = 0.0, *, width: int = 640) -> str:
        try:
            thumb_path = thumbnail_cache_path(
                str(path or ""),
                max(0.0, float(sec or 0.0)),
                self._thumbnail_cache_dir(),
                width=max(160, int(width or 640)),
            )
        except Exception:
            return ""
        return str(thumb_path) if thumb_path else ""

    def _show_precomputed_thumbnail_at(self, path: str, sec: float = 0.0, *, width: int = 640) -> bool:
        thumb_path = self._cached_thumbnail_path(path, sec, width=width)
        if not thumb_path or not os.path.exists(thumb_path):
            return False
        return self._show_thumbnail_from_cache_path(thumb_path)

    def _schedule_initial_thumbnail_prepare(self, path: str, sec: float = 0.0, *, width: int = 640, delay_ms: int = 160) -> None:
        if not self._is_video_file(path):
            return
        request_key = self._thumbnail_request_key(path, sec, width=width)
        self._initial_thumbnail_request_key = request_key
        if self._show_precomputed_thumbnail_at(path, sec, width=width):
            return

        def _start_worker() -> None:
            if self._initial_thumbnail_request_key != request_key:
                return
            if os.path.normpath(str(getattr(self, "_current_source_path", "") or "")) != os.path.normpath(str(path or "")):
                return

            def _worker() -> None:
                result = ensure_thumbnail(
                    path,
                    max(0.0, float(sec or 0.0)),
                    cache_dir=self._thumbnail_cache_dir(),
                    width=max(160, int(width or 640)),
                )
                if result.status not in ("cached", "created") or not result.path:
                    return
                try:
                    self.initial_thumbnail_ready.emit(request_key, str(result.path))
                except RuntimeError:
                    return

            try:
                threading.Thread(
                    target=_worker,
                    daemon=True,
                    name="video-open-thumbnail",
                ).start()
            except Exception:
                pass

        QTimer.singleShot(max(0, int(delay_ms)), _start_worker)

    def _on_initial_thumbnail_ready(self, request_key: str, thumb_path: str) -> None:
        if str(request_key or "") != str(getattr(self, "_initial_thumbnail_request_key", "") or ""):
            return
        try:
            if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                return
        except Exception:
            pass
        self._show_thumbnail_from_cache_path(str(thumb_path or ""))

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
                try:
                    os.remove(thumb_path)
                except Exception:
                    pass
        except Exception:
            pass

    def _hide_thumbnail(self):
        if self.video_stack.currentIndex() == 1:
            self.video_stack.setCurrentIndex(0)

    def _paused_seek_should_keep_thumbnail(self) -> bool:
        try:
            if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                return False
        except Exception:
            return False
        return not bool(getattr(self, "_video_surface_primed", False))

    def _seek_hide_thumbnail_threshold(self, default_threshold: float | None) -> float | None:
        if self._paused_seek_should_keep_thumbnail():
            return None
        return default_threshold

    def _show_unprimed_seek_thumbnail(self, sec: float, *, force: bool = False) -> None:
        if not self._paused_seek_should_keep_thumbnail():
            return
        source_path = str(getattr(self, "_current_source_path", "") or getattr(self, "_proxy_original_path", "") or "")
        if not source_path or not self._is_video_file(source_path):
            return
        try:
            sec = self._normalize_seek_sec(sec)
        except Exception:
            sec = max(0.0, float(sec or 0.0))
        now = time.monotonic()
        last_sec = getattr(self, "_last_unprimed_thumbnail_sec", None)
        try:
            near_same = last_sec is not None and abs(float(last_sec) - sec) < 0.08
        except Exception:
            near_same = False
        if not force:
            elapsed = now - float(getattr(self, "_last_unprimed_thumbnail_at", 0.0) or 0.0)
            if elapsed < 0.18 or (near_same and elapsed < 0.45):
                return
        self._last_unprimed_thumbnail_at = now
        self._last_unprimed_thumbnail_sec = sec
        self.show_cached_thumbnail_at(source_path, sec, width=640)

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

    def _normalize_seek_sec(
        self,
        sec: float,
        *,
        clamp_total: bool = False,
        frame_hint: int | None = None,
    ) -> float:
        try:
            sec = max(0.0, float(sec or 0.0))
        except Exception:
            sec = 0.0
        if clamp_total and self.total_time > 0.0:
            sec = min(sec, max(0.0, float(self.total_time or 0.0)))
        frame_map = getattr(self, "frame_time_map", None)
        if frame_map is None:
            frame_map = build_frame_time_map(self.total_time, self.frame_rate)
            self.frame_time_map = frame_map
        if frame_hint is None:
            frame = sec_to_floor_frame(sec, getattr(frame_map, "fps", self.frame_rate))
        else:
            try:
                frame = int(frame_hint)
            except Exception:
                frame = sec_to_floor_frame(sec, getattr(frame_map, "fps", self.frame_rate))
        if getattr(frame_map, "total_frames", 0) > 0:
            frame = max(0, min(frame, max(0, int(frame_map.total_frames) - 1)))
        return self.sec_for_frame(frame)

    def _sync_media_position_for_frame(self, frame: int) -> int:
        pos_ms = self.position_ms_for_frame(frame)
        if self._media_source_loaded:
            self.media_player.setPosition(pos_ms)
        if getattr(self, "has_vocal_track", False) and self._media_source_loaded:
            self._ensure_vocal_player().setPosition(pos_ms)
        return pos_ms

    def _apply_seek_state(
        self,
        sec: float,
        *,
        clamp_total: bool = False,
        remember_pending: bool = False,
        hide_thumbnail_threshold: float | None = None,
        refresh_provider: bool = False,
        refresh_subtitle: bool = True,
        tick_ui: bool = False,
        frame_hint: int | None = None,
    ) -> float:
        snapped_sec = self._normalize_seek_sec(sec, clamp_total=clamp_total, frame_hint=frame_hint)
        self.current_time = snapped_sec
        if frame_hint is None:
            self.current_frame = self.frame_for_sec(snapped_sec)
        else:
            try:
                self.current_frame = max(0, int(frame_hint))
            except Exception:
                self.current_frame = self.frame_for_sec(snapped_sec)
        self._update_frame_count_label()
        self.set_subtitle_display_time(snapped_sec, refresh=False)
        self._pending_seek_sec = float(snapped_sec) if remember_pending else None
        if hide_thumbnail_threshold is not None and snapped_sec > float(hide_thumbnail_threshold):
            self._hide_thumbnail()
        self._sync_media_position_for_frame(self.current_frame)
        if refresh_provider and bool(getattr(self, "_provider_refresh_requested", False)):
            self._refresh_provider_segments(force=False)
        if refresh_subtitle:
            self._refresh_subtitle_now()
        if tick_ui and hasattr(self, "_ui_tick"):
            self._ui_tick()
        return snapped_sec

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

    def _frame_count_text(self) -> str:
        frame_map = getattr(self, "frame_time_map", None)
        if frame_map is None:
            frame_map = build_frame_time_map(self.total_time, self.frame_rate)
            self.frame_time_map = frame_map
        total_frames = max(0, int(getattr(frame_map, "total_frames", 0) or 0))
        current_frame = max(0, int(getattr(self, "current_frame", 0) or 0))
        if total_frames > 0:
            current_frame = min(current_frame, total_frames - 1)
        return f"F {current_frame} / {total_frames}"

    def _update_frame_count_label(self, *, force: bool = False) -> None:
        label = getattr(self, "frame_count_label", None)
        if label is None:
            return
        text = self._frame_count_text()
        if force or text != getattr(self, "_last_frame_count_text", ""):
            self._last_frame_count_text = text
            label.setText(text)
        label.show()

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
        self._video_surface_primed = False
        self._pending_segments = segments
        self._pending_seek_sec = seek_sec
        self._pending_autoplay = bool(autoplay)
        self._pending_thumb_path = path if show_thumbnail and self._is_video_file(path) else None
        self._pending_thumb_sec = seek_sec if show_thumbnail else 0.0
        self.load(path, segments)

    def set_active_context(self, path: str, segments: list[dict] | None = None, seek_sec: float = 0.0, autoplay: bool = False, show_thumbnail: bool = True):
        self.load_clip_context(path, segments=segments, seek_sec=seek_sec, autoplay=autoplay, show_thumbnail=show_thumbnail)


    def seek_direct(self, sec):
        snapped = self._apply_seek_state(sec, remember_pending=False, refresh_provider=True)
        self._show_unprimed_seek_thumbnail(snapped, force=True)

    def preview_seek(self, sec: float):
        """Lightweight seek for timeline scrubbing.

        This updates the media position and visible subtitle without forcing the
        subtitle provider or thumbnail pipeline on every mouse-move event.
        """
        snapped = self._apply_seek_state(
            sec,
            remember_pending=False,
            hide_thumbnail_threshold=self._seek_hide_thumbnail_threshold(0.05),
            refresh_provider=False,
        )
        self._show_unprimed_seek_thumbnail(snapped)

    def frame_step_seek(self, sec: float):
        """Frame-exact manual seek used by < / > and scan buttons."""
        frame_hint = self.frame_for_sec(sec)
        snapped = self._apply_seek_state(
            sec,
            clamp_total=True,
            remember_pending=False,
            hide_thumbnail_threshold=self._seek_hide_thumbnail_threshold(-1.0),
            refresh_provider=False,
            tick_ui=True,
            frame_hint=frame_hint,
        )
        self._show_unprimed_seek_thumbnail(snapped, force=True)

    def seek(self, sec: float):
        snapped = self._apply_seek_state(
            sec,
            remember_pending=True,
            hide_thumbnail_threshold=self._seek_hide_thumbnail_threshold(0.05),
            refresh_provider=True,
        )
        self._show_unprimed_seek_thumbnail(snapped, force=True)


    def request_scan_cut(self, direction: int):
        try:
            direction = 1 if int(direction) > 0 else -1
        except Exception:
            direction = 1
        self.scan_cut_requested.emit(direction)

    def request_frame_step(self, direction: int):
        try:
            step = int(direction or 0)
        except Exception:
            step = 1
        if step == 0:
            return
        self.pause_video()
        owner = self
        visited: set[int] = set()
        while owner is not None and id(owner) not in visited:
            visited.add(id(owner))
            handler = getattr(owner, "_on_step_frame", None)
            if callable(handler):
                try:
                    handler(step)
                    return
                except Exception:
                    break
            next_owner = None
            try:
                next_owner = owner.parentWidget()
            except Exception:
                next_owner = None
            if next_owner is None:
                try:
                    next_owner = owner.parent()
                except Exception:
                    next_owner = None
            owner = next_owner
        self.frame_step_requested.emit(step)


    def toggle_play(self):
        if not getattr(self, '_source_ready', True):
            self._pending_autoplay = True
            return
        starting = self.media_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState
        if starting:
            prepare_repeat = getattr(self, "_repeat_play_prepare_callback", None)
            if callable(prepare_repeat):
                try:
                    prepare_repeat()
                except Exception:
                    pass
        self._ensure_audio_outputs()
        if not self._ensure_media_source_loaded():
            self._pending_autoplay = True
            return
        self._hide_thumbnail()
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            if getattr(self, 'has_vocal_track', False):
                self._ensure_vocal_player().pause()
        else:
            if bool(getattr(self, "_provider_refresh_requested", False)):
                self._refresh_provider_segments(force=False)
            self._video_surface_primed = True
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
                self._ensure_vocal_player().setPosition(self.media_player.position())
            self.media_player.play()
            if getattr(self, 'has_vocal_track', False):
                self._ensure_vocal_player().play()
        self._update_btn()

    def pause_video(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            if getattr(self, 'has_vocal_track', False):
                self._ensure_vocal_player().pause()
            self._update_btn()

    def _update_btn(self):
        is_playing = self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        if self._last_btn_state == is_playing:
            return
        self._last_btn_state = is_playing
        self.btn_play.setText("⏸" if is_playing else "▶")
        self._sync_quick_control_bar()

    def _ui_tick(self):
        self._update_btn()
        if not getattr(self, '_source_ready', True):
            return
        is_playing = self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        target_interval = self._play_ui_interval_ms if is_playing else self._idle_ui_interval_ms
        try:
            if int(self._ui_timer.interval()) != int(target_interval):
                self._ui_timer.setInterval(int(target_interval))
        except Exception:
            pass
        if is_playing:
            self.current_playback_frame_time()
            self.set_subtitle_display_time(self.current_time, refresh=False)
        else:
            if bool(getattr(self, "_provider_refresh_requested", False)):
                self._refresh_provider_segments(force=False)

        def format_time(sec):
            m, s = divmod(int(sec), 60)
            return f"{m:02d}:{s:02d}"

        pos_ms = int(self.current_time * 1000)
        if abs(pos_ms - self._last_time_label_ms) >= 250:
            self._last_time_label_ms = pos_ms
            self.time_label.setText(f"{format_time(self.current_time)} / {format_time(self.total_time)}")
        self._update_frame_count_label()
        
        self._refresh_subtitle_now()

    def closeEvent(self, event):
        self.shutdown_backend()
        super().closeEvent(event)

    def _release_cached_surfaces(self):
        self.segments = []
        self._subtitle_starts = []
        self._subtitle_ends = []
        self._subtitle_texts = []
        self._subtitle_count = 0
        self._subtitle_cache_idx = -1
        self._subtitle_provider = None
        self._subtitle_provider_segments_ref = None
        self._subtitle_provider_signature = ""
        self._context_segments_ref = None
        self._context_segments_signature = ""
        self._initial_thumbnail_request_key = ""
        self._pending_segments = None
        self._pending_seek_sec = None
        self._pending_thumb_path = None
        self._pending_thumb_sec = 0.0
        self._last_sub = ""
        self._last_time_label_ms = -250
        self._last_frame_count_text = ""
        self._current_source_path = ""
        self._source_display_name = ""
        self._source_media_info = {}
        self._source_info_status_text = ""
        self._source_preview_label = ""
        try:
            self.set_subtitle_display_time(None, refresh=False)
        except Exception:
            self._subtitle_display_time_sec = None
        try:
            self._set_subtitle_overlay_text("")
        except Exception:
            pass
        try:
            self.thumb_label.clear_pixmap()
        except Exception:
            pass
        try:
            self._refresh_source_info_label()
            self.frame_count_label.setText("F 0 / 0")
            self.frame_count_label.show()
            self._refresh_source_name_label()
        except Exception:
            pass

    def shutdown_backend(self):
        if bool(getattr(self, "_shutdown_in_progress", False)):
            return
        self._shutdown_in_progress = True
        try:
            self.setUpdatesEnabled(False)
        except Exception:
            pass
        for attr in ("_ui_timer", "_frame_step_hold_timer", "_frame_step_hold_start_timer"):
            timer = getattr(self, attr, None)
            try:
                if timer is not None:
                    timer.stop()
            except Exception:
                pass
        try:
            proc = getattr(self, "_proxy_build_proc", None)
            if proc is not None and proc.poll() is None:
                proc.terminate()
        except Exception:
            pass
        self._proxy_build_proc = None
        self._release_cached_surfaces()
        for widget_name in ("quick_subtitle_overlay", "_quick_control_bar", "sub_label", "thumb_label", "video_stack"):
            widget = getattr(self, widget_name, None)
            try:
                if widget is not None:
                    widget.hide()
                    widget.setUpdatesEnabled(False)
            except Exception:
                pass
        try:
            self.media_player.durationChanged.disconnect(self._on_duration_changed)
        except Exception:
            pass
        try:
            self.media_player.mediaStatusChanged.disconnect(self._on_media_status_changed)
        except Exception:
            pass
        seen_players = set()
        for player_name in ("media_player", "vocal_player", "audio_player"):
            player = getattr(self, player_name, None)
            if player is None or id(player) in seen_players:
                continue
            seen_players.add(id(player))
            try:
                if hasattr(player, "stop"):
                    player.stop()
            except Exception:
                pass
            try:
                if hasattr(player, "setVideoOutput"):
                    player.setVideoOutput(None)
            except Exception:
                pass
            try:
                if hasattr(player, "setAudioOutput"):
                    player.setAudioOutput(None)
            except Exception:
                pass
            try:
                if hasattr(player, "setSource"):
                    player.setSource(QUrl())
            except Exception:
                pass
        try:
            self._release_vocal_player()
        except Exception:
            pass
        for output_name in ("audio_output", "vocal_audio_output"):
            output = getattr(self, output_name, None)
            if output is None:
                continue
            try:
                output.deleteLater()
            except Exception:
                pass
            setattr(self, output_name, None)
