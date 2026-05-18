from __future__ import annotations

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer

from core.runtime.logger import get_logger


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
    def _play(self):
        return self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    @_play.setter
    def _play(self, value):
        del value

    def set_playing(self, playing: bool):
        if playing:
            self.parent_widget._video_surface_primed = True
            self.media_player.play()
            if getattr(self.parent_widget, "has_vocal_track", False):
                vocal_player = self.parent_widget._ensure_vocal_player()
                vocal_player.setPosition(self.media_player.position())
                vocal_player.play()
        else:
            self.media_player.pause()
            if getattr(self.parent_widget, "has_vocal_track", False):
                self.parent_widget._ensure_vocal_player().pause()

    def stop(self):
        self.media_player.stop()
        if getattr(self.parent_widget, "has_vocal_track", False):
            self.parent_widget._ensure_vocal_player().stop()

    def wait(self, _timeout_ms=None):
        return True

    def seek(self, sec):
        parent = self.parent_widget
        parent._apply_seek_state(
            sec,
            remember_pending=True,
            hide_thumbnail_threshold=0.05,
            refresh_provider=False,
            refresh_subtitle=False,
        )


class VideoPlayerAudioMixin:
    def _log_video_audio_nonfatal(self, stage: str, exc: Exception) -> None:
        try:
            get_logger().log(f"⚠️ [video-audio:{stage}] {type(exc).__name__}: {exc}")
        except Exception:
            return

    def _ensure_audio_outputs(self) -> None:
        """Create Qt audio outputs lazily to avoid startup crashes on some macOS audio setups."""
        audio_output_cls = getattr(self, "_qaudio_output_cls", QAudioOutput)
        try:
            if bool(getattr(self.media_player, "uses_qt_audio", False)):
                if self.audio_output is None:
                    self.audio_output = audio_output_cls(self)
                self.media_player.setAudioOutput(self.audio_output)
            if self.has_vocal_track:
                vocal_player = self._ensure_vocal_player()
                if self.vocal_audio_output is None:
                    self.vocal_audio_output = audio_output_cls(self)
                vocal_player.setAudioOutput(self.vocal_audio_output)
        except Exception as exc:
            self.audio_output = None
            self.vocal_audio_output = None
            self._log_video_audio_nonfatal("ensure_outputs", exc)

    def _connect_audio_device_signals(self) -> None:
        media_devices_cls = getattr(self, "_media_devices_cls", QMediaDevices)
        try:
            self._media_devices = media_devices_cls(self)
            self._media_devices.audioOutputsChanged.connect(self._on_audio_outputs_changed)
        except Exception as exc:
            self._media_devices = None
            self._log_video_audio_nonfatal("connect_device_signals", exc)

    def _on_audio_outputs_changed(self) -> None:
        if bool(getattr(self, "_shutdown_in_progress", False)):
            return
        QTimer.singleShot(0, lambda: self.refresh_audio_output_routing(reason="audio_outputs_changed"))

    def refresh_audio_output_routing(self, *, reason: str = "") -> None:
        del reason
        if bool(getattr(self, "_shutdown_in_progress", False)):
            return
        if bool(getattr(self, "_audio_rebind_in_progress", False)):
            return

        main_player = getattr(self, "media_player", None)
        uses_main_qt_audio = bool(getattr(main_player, "uses_qt_audio", False))
        vocal_player = getattr(self, "vocal_player", None) if getattr(self, "has_vocal_track", False) else None
        uses_vocal_qt_audio = vocal_player is not None and hasattr(vocal_player, "setAudioOutput")
        if not uses_main_qt_audio and not uses_vocal_qt_audio:
            return

        self._audio_rebind_in_progress = True
        try:
            main_was_playing = bool(
                uses_main_qt_audio
                and hasattr(main_player, "playbackState")
                and main_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            )
            vocal_was_playing = bool(
                uses_vocal_qt_audio
                and hasattr(vocal_player, "playbackState")
                and vocal_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            )
            main_position_ms = int(main_player.position() or 0) if uses_main_qt_audio and hasattr(main_player, "position") else 0
            vocal_position_ms = (
                int(vocal_player.position() or main_position_ms)
                if uses_vocal_qt_audio and hasattr(vocal_player, "position")
                else main_position_ms
            )

            if main_was_playing and hasattr(main_player, "pause"):
                try:
                    main_player.pause()
                except Exception as exc:
                    self._log_video_audio_nonfatal("rebind_pause_main", exc)
            if vocal_was_playing and hasattr(vocal_player, "pause"):
                try:
                    vocal_player.pause()
                except Exception as exc:
                    self._log_video_audio_nonfatal("rebind_pause_vocal", exc)

            bindings = (
                (main_player, getattr(self, "audio_output", None)),
                (vocal_player, getattr(self, "vocal_audio_output", None)),
            )
            for player, output in bindings:
                if player is None or output is None or not hasattr(player, "setAudioOutput"):
                    continue
                try:
                    player.setAudioOutput(None)
                except Exception as exc:
                    self._log_video_audio_nonfatal("rebind_detach_output", exc)

            for output_name in ("audio_output", "vocal_audio_output"):
                output = getattr(self, output_name, None)
                if output is None:
                    continue
                try:
                    output.deleteLater()
                except Exception as exc:
                    self._log_video_audio_nonfatal("rebind_delete_output", exc)
                setattr(self, output_name, None)

            self._ensure_audio_outputs()

            if self.audio_output is not None:
                try:
                    self.audio_output.setVolume(1.0)
                except Exception as exc:
                    self._log_video_audio_nonfatal("rebind_volume_main", exc)
            if self.vocal_audio_output is not None:
                try:
                    self.vocal_audio_output.setVolume(1.0)
                except Exception as exc:
                    self._log_video_audio_nonfatal("rebind_volume_vocal", exc)

            if uses_main_qt_audio and hasattr(main_player, "setPosition"):
                try:
                    main_player.setPosition(main_position_ms)
                except Exception as exc:
                    self._log_video_audio_nonfatal("rebind_restore_main_position", exc)
            if uses_vocal_qt_audio and vocal_player is not None and hasattr(vocal_player, "setPosition"):
                try:
                    vocal_player.setPosition(vocal_position_ms)
                except Exception as exc:
                    self._log_video_audio_nonfatal("rebind_restore_vocal_position", exc)

            if main_was_playing and hasattr(main_player, "play"):
                try:
                    main_player.play()
                except Exception as exc:
                    self._log_video_audio_nonfatal("rebind_resume_main", exc)
            if vocal_was_playing and hasattr(vocal_player, "play"):
                try:
                    vocal_player.play()
                except Exception as exc:
                    self._log_video_audio_nonfatal("rebind_resume_vocal", exc)
        finally:
            self._audio_rebind_in_progress = False

    def _ensure_vocal_player(self) -> QMediaPlayer:
        player = getattr(self, "vocal_player", None)
        if isinstance(player, QMediaPlayer):
            return player
        player = QMediaPlayer(self)
        self.vocal_player = player
        if self.vocal_audio_output is not None:
            try:
                player.setAudioOutput(self.vocal_audio_output)
            except Exception as exc:
                self._log_video_audio_nonfatal("ensure_vocal_bind_output", exc)
        return player

    def _release_vocal_player(self) -> None:
        player = getattr(self, "vocal_player", None)
        if isinstance(player, QMediaPlayer):
            try:
                player.stop()
            except Exception as exc:
                self._log_video_audio_nonfatal("release_vocal_stop", exc)
            try:
                player.setAudioOutput(None)
            except Exception as exc:
                self._log_video_audio_nonfatal("release_vocal_detach_output", exc)
            try:
                player.setSource(QUrl())
            except Exception as exc:
                self._log_video_audio_nonfatal("release_vocal_clear_source", exc)
            try:
                player.deleteLater()
            except Exception as exc:
                self._log_video_audio_nonfatal("release_vocal_delete", exc)
        self.vocal_player = _DormantAuxPlayer()
        self.vocal_audio_output = None


__all__ = ["_DormantAuxPlayer", "_WorkerProxy", "VideoPlayerAudioMixin"]
