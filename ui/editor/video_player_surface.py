from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QPixmap
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtWidgets import QSizePolicy, QStackedWidget, QWidget

from core.frame_time import build_frame_time_map, normalize_fps
from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs
from core.roughcut import default_thumbnail_cache_dir, ensure_thumbnail, thumbnail_cache_path
from core.runtime import config
from core.runtime.logger import get_logger
from core.video_codec import ffmpeg_hwdecode_args, hevc_encode_args
from core.video_preview_proxy import preview_proxy_path_for, register_preview_proxy_created
from ui.editor.video_overlay_widgets import (
    ThumbnailLabel,
    SubtitleLabel,
    SubtitleQuickOverlay,
    VideoSurfaceView,
)


class VideoPlayerSurfaceMixin:
    def _log_video_surface_nonfatal(self, stage: str, exc: Exception) -> None:
        try:
            get_logger().log(f"⚠️ [video-surface:{stage}] {type(exc).__name__}: {exc}")
        except Exception:
            return

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
        self._refresh_time_label(force=True)
        self._update_frame_count_label(force=True)

    def _apply_loaded_media_state(self):
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
        from PyQt6.QtMultimedia import QMediaPlayer as _QMP

        if status in (_QMP.MediaStatus.LoadedMedia, _QMP.MediaStatus.BufferedMedia):
            self._apply_loaded_media_state()
        if status == _QMP.MediaStatus.EndOfMedia:
            cb = getattr(self, "_end_of_media_callback", None)
            if callable(cb):
                cb()

    def _on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._video_surface_primed = True
            self._hide_thumbnail()
        self._update_btn()

    def _fallback_to_qt_video_backend(self, reason: Exception | str):
        try:
            get_logger().log(f"  ⚠️ [비디오] mpv 미리보기 초기화 실패 → Qt 백엔드로 전환: {reason}")
        except Exception:
            return
        old_player = getattr(self, "media_player", None)
        try:
            if old_player is not None and hasattr(old_player, "stop"):
                old_player.stop()
        except Exception as exc:
            self._log_video_surface_nonfatal("fallback_stop_old_backend", exc)
        try:
            if old_player is not None and hasattr(old_player, "deleteLater"):
                old_player.deleteLater()
        except Exception as exc:
            self._log_video_surface_nonfatal("fallback_delete_old_backend", exc)
        player = QMediaPlayer(self)
        player.backend_name = "qt"  # type: ignore[attr-defined]
        player.uses_qt_audio = True  # type: ignore[attr-defined]
        self.media_player = player
        self.audio_player = player
        self.audio_output = None
        try:
            self._worker.media_player = player
        except Exception as exc:
            self._log_video_surface_nonfatal("fallback_bind_worker", exc)
        player.durationChanged.connect(self._on_duration_changed)
        player.mediaStatusChanged.connect(self._on_media_status_changed)
        try:
            player.playbackStateChanged.connect(self._on_playback_state_changed)
        except Exception as exc:
            self._log_video_surface_nonfatal("fallback_connect_playback_state", exc)
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

    def _get_audio_ai_setting(self) -> str:
        try:
            settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    return json.load(f).get("selected_audio_ai", "deepfilter")
        except Exception as exc:
            self._log_video_surface_nonfatal("load_audio_ai_setting", exc)
        return "deepfilter"

    def _is_video_file(self, path: str) -> bool:
        return os.path.splitext(path)[1].lower() in {
            ".mp4",
            ".mov",
            ".m4v",
            ".mkv",
            ".avi",
            ".webm",
            ".mts",
            ".m2ts",
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
                except Exception as exc:
                    self._log_video_surface_nonfatal("set_proxy_build_status", exc)
                return ""
            if self._source_needs_preview_proxy():
                try:
                    self._set_source_info_status("720p 프리뷰 준비 중")
                except Exception as exc:
                    self._log_video_surface_nonfatal("set_proxy_wait_status", exc)
        return path

    def _source_needs_preview_proxy(self) -> bool:
        try:
            width = int(getattr(self, "_source_width", 0) or 0)
            height = int(getattr(self, "_source_height", 0) or 0)
            return bool(
                width > int(getattr(self, "_preview_max_width", 1280) or 1280)
                or height > int(getattr(self, "_preview_max_height", 720) or 720)
            )
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
        except Exception as exc:
            self._log_video_surface_nonfatal("load_proxy_wait_setting", exc)
        return False

    def _start_proxy_build(self, src: str, dst: str):
        subprocess_module = getattr(self, "_subprocess_module", subprocess)
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
            self._proxy_build_proc = subprocess_module.Popen(
                cmd,
                stdout=subprocess_module.DEVNULL,
                stderr=subprocess_module.DEVNULL,
                **hidden_subprocess_kwargs(strip_qt=True),
            )
            QTimer.singleShot(500, lambda s=src, t=tmp_dst, d=dst: self._poll_proxy_build(s, t, d))
        except Exception as exc:
            self._proxy_build_proc = None
            self._log_video_surface_nonfatal("start_proxy_build", exc)

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
        except OSError as exc:
            self._log_video_surface_nonfatal("promote_proxy_build", exc)
            return
        try:
            register_preview_proxy_created(dst)
        except Exception as exc:
            self._log_video_surface_nonfatal("register_proxy_build", exc)
        if os.path.normpath(getattr(self, "_current_source_path", "") or "") == os.path.normpath(src):
            self._switch_to_proxy(dst)

    def _switch_to_proxy(self, _proxy_path: str):
        if not _proxy_path or not os.path.exists(_proxy_path):
            return
        try:
            was_playing = self.media_player.playbackState() == self.media_player.PlaybackState.PlayingState
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
        except Exception as exc:
            self._log_video_surface_nonfatal("switch_to_proxy", exc)

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
        except Exception as exc:
            self._log_video_surface_nonfatal("load_preview_proxy_setting", exc)
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
                except Exception as exc:
                    self._source_aspect = 16 / 9
                    self._source_width = 0
                    self._source_height = 0
                    self._log_video_surface_nonfatal("probe_media", exc)
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
        subprocess_module = getattr(self, "_subprocess_module", subprocess)
        if not self._is_video_file(path):
            return
        if self.media_player.playbackState() == self.media_player.PlaybackState.PlayingState:
            return
        self.video_stack.setCurrentIndex(1)
        temp_dir = tempfile.gettempdir()
        thumb_path = os.path.join(temp_dir, "thumb_temp_cpd.jpg")
        sec = max(0.0, float(sec))
        hh = int(sec // 3600)
        mm = int((sec % 3600) // 60)
        ss = sec % 60.0
        ts = f"{hh:02d}:{mm:02d}:{ss:06.3f}"
        cmd = ["ffmpeg", "-y", "-ss", ts, *ffmpeg_hwdecode_args(), "-i", path, "-frames:v", "1", "-q:v", "2", thumb_path]
        kwargs = {"stdout": subprocess_module.DEVNULL, "stderr": subprocess_module.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000
        try:
            subprocess_module.run(cmd, check=True, timeout=3.0, **kwargs)
            if os.path.exists(thumb_path):
                pixmap = QPixmap(thumb_path)
                if not pixmap.isNull():
                    self.thumb_label.set_pixmap(pixmap)
                try:
                    os.remove(thumb_path)
                except Exception as exc:
                    self._log_video_surface_nonfatal("remove_seek_thumbnail_temp", exc)
        except Exception as exc:
            self._log_video_surface_nonfatal("extract_seek_thumbnail", exc)

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
        except Exception as exc:
            self._log_video_surface_nonfatal("resolve_thumbnail_cache_path", exc)
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
            except Exception as exc:
                self._log_video_surface_nonfatal("start_initial_thumbnail_worker", exc)

        QTimer.singleShot(max(0, int(delay_ms)), _start_worker)

    def _on_initial_thumbnail_ready(self, request_key: str, thumb_path: str) -> None:
        if str(request_key or "") != str(getattr(self, "_initial_thumbnail_request_key", "") or ""):
            return
        try:
            if self.media_player.playbackState() == self.media_player.PlaybackState.PlayingState:
                return
        except Exception as exc:
            self._log_video_surface_nonfatal("initial_thumbnail_playback_state", exc)
        self._show_thumbnail_from_cache_path(str(thumb_path or ""))

    def show_cached_thumbnail_at(self, path: str, sec: float = 0.0, *, width: int = 640) -> bool:
        if not self._is_video_file(path):
            return False
        if self.media_player.playbackState() == self.media_player.PlaybackState.PlayingState:
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
        subprocess_module = getattr(self, "_subprocess_module", subprocess)
        if not self._is_video_file(path):
            return
        if self.media_player.playbackState() == self.media_player.PlaybackState.PlayingState:
            return
        self.video_stack.setCurrentIndex(1)
        temp_dir = tempfile.gettempdir()
        thumb_path = os.path.join(temp_dir, "thumb_temp_cpd.jpg")

        cmd = ["ffmpeg", "-y", "-ss", "00:00:00", *ffmpeg_hwdecode_args(), "-i", path, "-frames:v", "1", "-q:v", "2", thumb_path]
        kwargs = {"stdout": subprocess_module.DEVNULL, "stderr": subprocess_module.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000

        try:
            subprocess_module.run(cmd, check=True, timeout=3.0, **kwargs)
            if os.path.exists(thumb_path):
                pixmap = QPixmap(thumb_path)
                if not pixmap.isNull():
                    self.thumb_label.set_pixmap(pixmap)
                try:
                    os.remove(thumb_path)
                except Exception as exc:
                    self._log_video_surface_nonfatal("remove_open_thumbnail_temp", exc)
        except Exception as exc:
            self._log_video_surface_nonfatal("extract_open_thumbnail", exc)

    def _hide_thumbnail(self):
        if self.video_stack.currentIndex() == 1:
            self.video_stack.setCurrentIndex(0)

    def _paused_seek_should_keep_thumbnail(self) -> bool:
        try:
            if self.media_player.playbackState() == self.media_player.PlaybackState.PlayingState:
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

    def load_clip_context(self, path, segments=None, seek_sec=0.0, autoplay=False, show_thumbnail=True):
        segments = list(segments or [])
        seek_sec = max(0.0, float(seek_sec))
        self._set_segments(segments)
        same_file = os.path.normpath(getattr(self, "_current_source_path", "") or "") == os.path.normpath(path)
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

    def suspend_for_navigation(self) -> None:
        try:
            self.pause_video()
        except Exception as exc:
            self._log_video_surface_nonfatal("suspend_pause_video", exc)
        try:
            if not self._ui_timer.isActive():
                self._ui_timer.start()
        except Exception as exc:
            self._log_video_surface_nonfatal("suspend_restart_ui_timer", exc)

    def compact_for_home_navigation(self) -> None:
        if bool(getattr(self, "_home_compact_mode", False)):
            return
        self._home_compact_mode = True
        try:
            self.pause_video()
        except Exception as exc:
            self._log_video_surface_nonfatal("compact_pause_video", exc)
        for attr in ("_ui_timer", "_frame_step_hold_timer", "_frame_step_hold_start_timer"):
            timer = getattr(self, attr, None)
            try:
                if timer is not None:
                    timer.stop()
            except Exception as exc:
                self._log_video_surface_nonfatal(f"compact_stop_timer:{attr}", exc)
        try:
            self.setUpdatesEnabled(False)
        except Exception as exc:
            self._log_video_surface_nonfatal("compact_disable_updates", exc)
        for widget_name in ("quick_subtitle_overlay", "_quick_control_bar", "sub_label", "thumb_label", "video_stack"):
            widget = getattr(self, widget_name, None)
            try:
                if widget is not None:
                    widget.hide()
                    widget.setUpdatesEnabled(False)
            except Exception as exc:
                self._log_video_surface_nonfatal(f"compact_hide_widget:{widget_name}", exc)
        try:
            if hasattr(self.media_player, "setVideoOutput"):
                self.media_player.setVideoOutput(None)
        except Exception as exc:
            self._log_video_surface_nonfatal("compact_detach_video_output", exc)
        for output_name in ("audio_output", "vocal_audio_output"):
            output = getattr(self, output_name, None)
            if output is None:
                continue
            try:
                output.deleteLater()
            except Exception as exc:
                self._log_video_surface_nonfatal(f"compact_delete_output:{output_name}", exc)
            setattr(self, output_name, None)
        try:
            self.thumb_label.clear_pixmap()
        except Exception as exc:
            self._log_video_surface_nonfatal("compact_clear_thumbnail", exc)

    def restore_after_navigation(self) -> None:
        was_shutdown = bool(getattr(self, "_shutdown_in_progress", False))
        self._home_compact_mode = False
        self._shutdown_in_progress = False
        for widget_name in ("video_stack", "thumb_label", "sub_label", "quick_subtitle_overlay"):
            widget = getattr(self, widget_name, None)
            try:
                if widget is not None:
                    widget.setUpdatesEnabled(True)
                    if widget_name in {"video_stack", "thumb_label"}:
                        widget.show()
            except Exception as exc:
                self._log_video_surface_nonfatal(f"restore_widget:{widget_name}", exc)
        quick_bar = getattr(self, "_quick_control_bar", None)
        try:
            if quick_bar is not None:
                quick_bar.setUpdatesEnabled(True)
                quick_bar.show()
        except Exception as exc:
            self._log_video_surface_nonfatal("restore_quick_bar", exc)
        try:
            self.setUpdatesEnabled(True)
            self.show()
        except Exception as exc:
            self._log_video_surface_nonfatal("restore_show_widget", exc)
        if was_shutdown:
            try:
                self.media_player.durationChanged.connect(self._on_duration_changed)
            except Exception as exc:
                self._log_video_surface_nonfatal("restore_connect_duration", exc)
            try:
                self.media_player.mediaStatusChanged.connect(self._on_media_status_changed)
            except Exception as exc:
                self._log_video_surface_nonfatal("restore_connect_status", exc)
        try:
            if hasattr(self.video_widget, "video_item"):
                self.media_player.setVideoOutput(self.video_widget.video_item)
        except Exception as exc:
            self._log_video_surface_nonfatal("restore_attach_video_output", exc)
        try:
            if not self._ui_timer.isActive():
                self._ui_timer.start()
        except Exception as exc:
            self._log_video_surface_nonfatal("restore_restart_ui_timer", exc)
        try:
            self._ensure_audio_outputs()
        except Exception as exc:
            self._log_video_surface_nonfatal("restore_audio_outputs", exc)
        try:
            if getattr(self, "_pending_media_source_path", ""):
                self._ensure_media_source_loaded()
                self._sync_media_position_for_frame(int(getattr(self, "current_frame", 0) or 0))
        except Exception as exc:
            self._log_video_surface_nonfatal("restore_pending_media_state", exc)
        try:
            source_path = str(getattr(self, "_current_source_path", "") or "")
            if not bool(getattr(self, "_video_surface_primed", False)) and self._is_video_file(source_path):
                self._show_precomputed_thumbnail_at(source_path, self.current_time) or self._show_precomputed_thumbnail_at(source_path, 0.0)
            else:
                self.video_stack.setCurrentIndex(0)
        except Exception as exc:
            self._log_video_surface_nonfatal("restore_surface_thumbnail", exc)
        try:
            self._refresh_source_info_label()
            self._refresh_source_name_label()
            self._update_frame_count_label(force=True)
            self._sync_quick_control_bar()
            self.resizeEvent(None)
            self.update()
        except Exception as exc:
            self._log_video_surface_nonfatal("restore_ui_refresh", exc)

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
        self.current_time = 0.0
        self.total_time = 0.0
        self.current_frame = 0
        try:
            self.set_subtitle_display_time(None, refresh=False)
        except Exception:
            self._subtitle_display_time_sec = None
        try:
            self._set_subtitle_overlay_text("")
        except Exception as exc:
            self._log_video_surface_nonfatal("release_overlay_text", exc)
        try:
            self.thumb_label.clear_pixmap()
        except Exception as exc:
            self._log_video_surface_nonfatal("release_thumbnail_pixmap", exc)
        try:
            self._refresh_source_info_label()
            self._refresh_time_label(force=True)
            self.frame_count_label.setText("F 0 / 0")
            self.frame_count_label.show()
            self._refresh_source_name_label()
        except Exception as exc:
            self._log_video_surface_nonfatal("release_labels", exc)

    def shutdown_backend(self):
        if bool(getattr(self, "_shutdown_in_progress", False)):
            return
        self._shutdown_in_progress = True
        try:
            self.setUpdatesEnabled(False)
        except Exception as exc:
            self._log_video_surface_nonfatal("shutdown_disable_updates", exc)
        for attr in ("_ui_timer", "_frame_step_hold_timer", "_frame_step_hold_start_timer"):
            timer = getattr(self, attr, None)
            try:
                if timer is not None:
                    timer.stop()
            except Exception as exc:
                self._log_video_surface_nonfatal(f"shutdown_stop_timer:{attr}", exc)
        try:
            proc = getattr(self, "_proxy_build_proc", None)
            if proc is not None and proc.poll() is None:
                proc.terminate()
        except Exception as exc:
            self._log_video_surface_nonfatal("shutdown_terminate_proxy", exc)
        self._proxy_build_proc = None
        self._release_cached_surfaces()
        for widget_name in ("quick_subtitle_overlay", "_quick_control_bar", "sub_label", "thumb_label", "video_stack"):
            widget = getattr(self, widget_name, None)
            try:
                if widget is not None:
                    widget.hide()
                    widget.setUpdatesEnabled(False)
            except Exception as exc:
                self._log_video_surface_nonfatal(f"shutdown_hide_widget:{widget_name}", exc)
        try:
            self.media_player.durationChanged.disconnect(self._on_duration_changed)
        except Exception as exc:
            self._log_video_surface_nonfatal("shutdown_disconnect_duration", exc)
        try:
            self.media_player.mediaStatusChanged.disconnect(self._on_media_status_changed)
        except Exception as exc:
            self._log_video_surface_nonfatal("shutdown_disconnect_status", exc)
        seen_players = set()
        for player_name in ("media_player", "vocal_player", "audio_player"):
            player = getattr(self, player_name, None)
            if player is None or id(player) in seen_players:
                continue
            seen_players.add(id(player))
            try:
                if hasattr(player, "stop"):
                    player.stop()
            except Exception as exc:
                self._log_video_surface_nonfatal(f"shutdown_stop_player:{player_name}", exc)
            try:
                if hasattr(player, "setVideoOutput"):
                    player.setVideoOutput(None)
            except Exception as exc:
                self._log_video_surface_nonfatal(f"shutdown_detach_video:{player_name}", exc)
            try:
                if hasattr(player, "setAudioOutput"):
                    player.setAudioOutput(None)
            except Exception as exc:
                self._log_video_surface_nonfatal(f"shutdown_detach_audio:{player_name}", exc)
            try:
                if hasattr(player, "setSource"):
                    player.setSource(QUrl())
            except Exception as exc:
                self._log_video_surface_nonfatal(f"shutdown_clear_source:{player_name}", exc)
        try:
            self._release_vocal_player()
        except Exception as exc:
            self._log_video_surface_nonfatal("shutdown_release_vocal", exc)
        for output_name in ("audio_output", "vocal_audio_output"):
            output = getattr(self, output_name, None)
            if output is None:
                continue
            try:
                output.deleteLater()
            except Exception as exc:
                self._log_video_surface_nonfatal(f"shutdown_delete_output:{output_name}", exc)
            setattr(self, output_name, None)


__all__ = ["VideoPlayerSurfaceMixin"]
