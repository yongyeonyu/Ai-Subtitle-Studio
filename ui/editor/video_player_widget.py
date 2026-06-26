# Version: 03.13.04
# Phase: PHASE2
"""
ui/video_player_widget.py - PyQt6 비디오 플레이어
[v01.00.01 버그수정] _get_audio_ai_setting: 미정의 변수 'paths' 참조 오류 제거
"""
import json
import os
import subprocess

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtGui import QColor

from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
from core.runtime import config
from core.frame_time import build_frame_time_map, normalize_fps, sec_to_floor_frame, snap_sec_to_frame
from ui.editor.video_playback_backend import create_video_backend
from ui.editor.video_player_audio import _DormantAuxPlayer, _WorkerProxy, VideoPlayerAudioMixin
from ui.editor.video_player_overlay_mixin import VideoPlayerOverlayMixin
from ui.editor.video_player_surface import VideoPlayerSurfaceMixin
from ui.editor.video_player_subtitles import VideoPlayerSubtitleMixin
from ui.editor.video_player_transport import VideoPlayerTransportMixin
from ui.gpu_rendering import scenegraph_enabled

class VideoPlayerWidget(
    VideoPlayerTransportMixin,
    VideoPlayerSurfaceMixin,
    VideoPlayerAudioMixin,
    VideoPlayerOverlayMixin,
    VideoPlayerSubtitleMixin,
    QWidget,
):
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
        self._home_compact_mode = False
        self._audio_rebind_in_progress = False
        self._media_devices = None
        self._qaudio_output_cls = QAudioOutput
        self._media_devices_cls = QMediaDevices
        self._subprocess_module = subprocess

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
        self._connect_audio_device_signals()

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

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(0)
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


    def _subtitle_lookup_time(self) -> float:
        override = getattr(self, "_subtitle_display_time_sec", None)
        if override is not None:
            return max(0.0, float(override))
        return max(0.0, float(getattr(self, "current_time", 0.0) or 0.0))

    def set_frame_rate(self, fps: float):
        self._rebuild_frame_time_map(fps=normalize_fps(fps))
        if hasattr(self, "_refresh_ui_timer_intervals"):
            self._refresh_ui_timer_intervals()

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
        if hasattr(self, "_refresh_time_label"):
            self._refresh_time_label(force=True)
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

    def _frame_display_values(self) -> tuple[int, int, int, float]:
        frame_map = getattr(self, "frame_time_map", None)
        if frame_map is None:
            frame_map = build_frame_time_map(self.total_time, self.frame_rate)
            self.frame_time_map = frame_map
        total_frames = max(0, int(getattr(frame_map, "total_frames", 0) or 0))
        current_frame = max(0, int(getattr(self, "current_frame", 0) or 0))
        display_frame = 0
        if total_frames > 0:
            current_frame = min(current_frame, total_frames - 1)
            display_frame = current_frame + 1
        fps = normalize_fps(getattr(frame_map, "fps", getattr(self, "frame_rate", 30.0)) or 30.0)
        return current_frame, display_frame, total_frames, fps

    def _format_frame_clock_time(self, sec: float) -> str:
        total_ms = max(0, int(round(float(sec or 0.0) * 1000.0)))
        hours, rem = divmod(total_ms, 3_600_000)
        minutes, rem = divmod(rem, 60_000)
        seconds, millis = divmod(rem, 1000)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
        return f"{minutes:02d}:{seconds:02d}.{millis:03d}"

    def _frame_time_label_text(self) -> str:
        current_frame, _display_frame, total_frames, fps = self._frame_display_values()
        current_sec = self.sec_for_frame(current_frame) if total_frames > 0 else 0.0
        total_sec = total_frames / max(fps, 1.0) if total_frames > 0 else 0.0
        return f"{self._format_frame_clock_time(current_sec)} / {self._format_frame_clock_time(total_sec)}"

    def _frame_count_text(self) -> str:
        _current_frame, display_frame, total_frames, _fps = self._frame_display_values()
        return f"{display_frame} / {total_frames}"

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

    def seek_direct(self, sec, *, show_thumbnail: bool = True):
        snapped = self._apply_seek_state(sec, remember_pending=False, refresh_provider=True)
        if show_thumbnail:
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
