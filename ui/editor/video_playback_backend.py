# Version: 03.17.00
# Phase: PHASE3
"""Selectable video playback backends for the editor preview.

QtMultimedia is the production-safe default. python-mpv/libmpv can be faster,
but on macOS it can abort the whole Python process from its native event thread
when embedded with the current PyQt/QML stack, so it is kept behind an explicit
unsafe experiment gate.
"""
from __future__ import annotations

import os
import sys
import json
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QObject, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtWidgets import QWidget

from core.runtime import config
from core.platform_compat import is_windows


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


@dataclass(frozen=True, slots=True)
class VideoBackendChoice:
    name: str
    reason: str


def _env_text(name: str) -> str:
    return str(os.environ.get(name, "") or "").strip().lower()


def _render_settings() -> dict:
    path = os.path.join(config.DATASET_DIR, "user_settings.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _settings_requested_video_backend() -> str:
    settings = _render_settings()
    for key in ("editor_video_backend", "video_playback_backend", "preview_video_backend"):
        value = str(settings.get(key, "") or "").strip().lower()
        if value:
            return value
    scope = str(settings.get("editor_rendering_gpu_scope", settings.get("gpu_rendering_scope", "")) or "").strip().lower()
    if scope in {"0", "false", "no", "off", "none", "disabled", "끄기", "끔"}:
        return "qt"
    return ""


def _coerce_bool(value, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return bool(value)
    text = str(value).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return bool(default)


def _embedded_mpv_enabled() -> bool:
    env_value = _env_text("AI_SUBTITLE_ENABLE_EMBEDDED_MPV")
    if env_value:
        return env_value in _TRUE_VALUES
    settings = _render_settings()
    return _coerce_bool(settings.get("editor_embedded_mpv_enabled"), False) or _coerce_bool(
        settings.get("editor_video_backend_unsafe_mpv_enabled"),
        False,
    )


def _running_under_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules


def _offscreen_qt() -> bool:
    return _env_text("QT_QPA_PLATFORM") == "offscreen"


def _module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def _mpv_available() -> bool:
    return _module_available("mpv")


def _vlc_available() -> bool:
    return _module_available("vlc")


def choose_video_backend(preferred: str | None = None) -> VideoBackendChoice:
    """Choose preview backend.

    `AI_SUBTITLE_VIDEO_BACKEND` can be `auto`, `mpv`, `vlc`, or `qt`.
    Tests and offscreen runs deliberately stay on Qt unless explicitly forced.
    """
    requested = str(preferred or os.environ.get("AI_SUBTITLE_VIDEO_BACKEND", "") or _settings_requested_video_backend() or "auto").strip().lower()
    if requested in {"qtmultimedia", "qtmedia"}:
        requested = "qt"
    if requested not in {"auto", "mpv", "vlc", "qt"}:
        requested = "auto"

    if requested == "qt":
        return VideoBackendChoice("qt", "forced")
    if (requested == "auto") and (_running_under_pytest() or _offscreen_qt()):
        return VideoBackendChoice("qt", "test_or_offscreen_safe")
    mpv_allowed = _embedded_mpv_enabled()
    if requested == "auto" and bool(getattr(config, "IS_MAC", False)) and not mpv_allowed:
        if _vlc_available():
            return VideoBackendChoice("vlc", "libvlc_fallback")
        return VideoBackendChoice("qt", "embedded_mpv_disabled")
    if requested == "mpv" and not mpv_allowed:
        return VideoBackendChoice("qt", "embedded_mpv_disabled")
    if requested in {"auto", "mpv"} and _mpv_available():
        return VideoBackendChoice("mpv", "preferred_lightweight_gpu_backend")
    if requested == "mpv":
        return VideoBackendChoice("qt", "mpv_unavailable")
    if requested in {"auto", "vlc"} and _vlc_available():
        return VideoBackendChoice("vlc", "libvlc_fallback")
    if requested == "vlc":
        return VideoBackendChoice("qt", "vlc_unavailable")
    return VideoBackendChoice("qt", "fallback")


class _BaseExternalBackend(QObject):
    durationChanged = pyqtSignal(int)
    mediaStatusChanged = pyqtSignal(object)

    backend_name = "external"
    uses_qt_audio = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source_path = ""
        self._video_widget: QWidget | None = None
        self._duration_ms = 0
        self._last_end_emitted = False
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(120)
        self._poll_timer.timeout.connect(self._poll)

    def create_video_widget(self, parent=None) -> QWidget:
        widget = QWidget(parent)
        widget.setStyleSheet("background: #000000;")
        widget.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self._video_widget = widget
        return widget

    def setVideoOutput(self, _output) -> None:
        return

    def setAudioOutput(self, _output) -> None:
        return

    def source(self) -> QUrl:
        return QUrl.fromLocalFile(self._source_path) if self._source_path else QUrl()

    def setSource(self, source: QUrl) -> None:
        self._source_path = source.toLocalFile() if hasattr(source, "toLocalFile") else str(source or "")
        self._last_end_emitted = False
        self._load_source(self._source_path)
        self.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.LoadedMedia)

    def playbackState(self):
        return QMediaPlayer.PlaybackState.PlayingState if self._is_playing() else QMediaPlayer.PlaybackState.PausedState

    def play(self) -> None:
        self._play()
        self._poll_timer.start()

    def pause(self) -> None:
        self._pause()
        self._poll()

    def stop(self) -> None:
        self._stop()
        self._poll_timer.stop()

    def position(self) -> int:
        return max(0, int(self._position_ms()))

    def setPosition(self, position_ms: int) -> None:
        self._set_position_ms(max(0, int(position_ms or 0)))
        self._last_end_emitted = False
        self._poll()

    def _poll(self) -> None:
        duration = max(0, int(self._duration()))
        if duration and duration != self._duration_ms:
            self._duration_ms = duration
            self.durationChanged.emit(duration)
        if duration and self.position() >= max(0, duration - 80) and not self._is_playing():
            if not self._last_end_emitted:
                self._last_end_emitted = True
                self.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.EndOfMedia)

    def _load_source(self, _path: str) -> None:  # pragma: no cover - abstract shim
        raise NotImplementedError

    def _play(self) -> None:  # pragma: no cover - abstract shim
        raise NotImplementedError

    def _pause(self) -> None:  # pragma: no cover - abstract shim
        raise NotImplementedError

    def _stop(self) -> None:  # pragma: no cover - abstract shim
        raise NotImplementedError

    def _is_playing(self) -> bool:  # pragma: no cover - abstract shim
        raise NotImplementedError

    def _position_ms(self) -> int:  # pragma: no cover - abstract shim
        raise NotImplementedError

    def _set_position_ms(self, _position_ms: int) -> None:  # pragma: no cover - abstract shim
        raise NotImplementedError

    def _duration(self) -> int:  # pragma: no cover - abstract shim
        raise NotImplementedError


class MpvPlaybackBackend(_BaseExternalBackend):
    backend_name = "mpv"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mpv: Any = None

    def create_video_widget(self, parent=None) -> QWidget:
        widget = super().create_video_widget(parent)
        self._ensure_player()
        return widget

    def _ensure_player(self) -> None:
        if self._mpv is not None:
            return
        import mpv  # type: ignore

        wid = int(self._video_widget.winId()) if self._video_widget is not None else 0
        base_kwargs = {
            "wid": str(wid) if wid else None,
            "hwdec": "auto-safe",
            "osc": False,
            "input_default_bindings": False,
            "input_vo_keyboard": False,
            "terminal": False,
        }
        base_kwargs = {key: value for key, value in base_kwargs.items() if value is not None}
        if bool(getattr(config, "IS_MAC", False)):
            attempts = [
                {**base_kwargs, "vo": "gpu-next", "gpu_api": "vulkan", "gpu_context": "macvk"},
                {**base_kwargs, "vo": "gpu-next", "gpu_api": "auto", "gpu_context": "auto"},
                {**base_kwargs, "vo": "gpu"},
            ]
        else:
            attempts = [
                {**base_kwargs, "vo": "gpu-next", "gpu_api": "auto", "gpu_context": "auto"},
                {**base_kwargs, "vo": "gpu"},
            ]
        last_exc: Exception | None = None
        for kwargs in attempts:
            try:
                self._mpv = mpv.MPV(**kwargs)
                break
            except Exception as exc:
                last_exc = exc
                self._mpv = None
        if self._mpv is None:
            raise RuntimeError(f"mpv backend init failed: {last_exc}")
        try:
            self._mpv.pause = True
        except Exception:
            pass

    def _load_source(self, path: str) -> None:
        self._ensure_player()
        if not path:
            return
        self._mpv.command("loadfile", path, "replace")
        try:
            self._mpv.pause = True
        except Exception:
            pass

    def _play(self) -> None:
        self._ensure_player()
        self._mpv.pause = False

    def _pause(self) -> None:
        if self._mpv is not None:
            self._mpv.pause = True

    def _stop(self) -> None:
        if self._mpv is not None:
            try:
                self._mpv.command("stop")
            except Exception:
                pass

    def _is_playing(self) -> bool:
        try:
            return bool(self._mpv is not None and not self._mpv.pause)
        except Exception:
            return False

    def _position_ms(self) -> int:
        try:
            return int(float(self._mpv.time_pos or 0.0) * 1000.0)
        except Exception:
            return 0

    def _set_position_ms(self, position_ms: int) -> None:
        self._ensure_player()
        try:
            self._mpv.time_pos = max(0.0, float(position_ms) / 1000.0)
        except Exception:
            try:
                self._mpv.command("seek", f"{float(position_ms) / 1000.0:.3f}", "absolute", "exact")
            except Exception:
                pass

    def _duration(self) -> int:
        try:
            return int(float(self._mpv.duration or 0.0) * 1000.0)
        except Exception:
            return self._duration_ms


class VlcPlaybackBackend(_BaseExternalBackend):
    backend_name = "vlc"

    def __init__(self, parent=None):
        super().__init__(parent)
        import vlc  # type: ignore

        self._vlc_mod = vlc
        self._instance = vlc.Instance("--quiet", "--no-video-title-show")
        self._player = self._instance.media_player_new()

    def create_video_widget(self, parent=None) -> QWidget:
        widget = super().create_video_widget(parent)
        handle = int(widget.winId())
        if sys.platform == "darwin":
            self._player.set_nsobject(handle)
        elif is_windows():
            self._player.set_hwnd(handle)
        else:
            self._player.set_xwindow(handle)
        return widget

    def _load_source(self, path: str) -> None:
        if not path:
            return
        media = self._instance.media_new(path)
        self._player.set_media(media)

    def _play(self) -> None:
        self._player.play()

    def _pause(self) -> None:
        self._player.pause()

    def _stop(self) -> None:
        self._player.stop()

    def _is_playing(self) -> bool:
        try:
            return bool(self._player.is_playing())
        except Exception:
            return False

    def _position_ms(self) -> int:
        try:
            return int(self._player.get_time())
        except Exception:
            return 0

    def _set_position_ms(self, position_ms: int) -> None:
        try:
            self._player.set_time(int(position_ms))
        except Exception:
            pass

    def _duration(self) -> int:
        try:
            return int(self._player.get_length())
        except Exception:
            return self._duration_ms


def create_video_backend(parent=None):
    choice = choose_video_backend()
    if choice.name == "mpv":
        try:
            return MpvPlaybackBackend(parent)
        except Exception:
            pass
    if choice.name in {"mpv", "vlc"} and _vlc_available():
        try:
            return VlcPlaybackBackend(parent)
        except Exception:
            pass
    player = QMediaPlayer(parent)
    player.backend_name = "qt"  # type: ignore[attr-defined]
    player.uses_qt_audio = True  # type: ignore[attr-defined]
    return player


__all__ = [
    "MpvPlaybackBackend",
    "VideoBackendChoice",
    "VlcPlaybackBackend",
    "choose_video_backend",
    "create_video_backend",
]
