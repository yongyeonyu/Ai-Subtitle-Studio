# Version: 03.09.07
# Phase: PHASE2
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import QObject, Qt, QRectF, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer

from core.frame_time import frame_to_sec
from core.runtime import config
from ui.editor.video_playback_backend import _BaseExternalBackend, choose_video_backend
from ui.editor.video_overlay_widgets import SubtitleQuickOverlay, VideoSurfaceView
from ui.editor.video_player_widget import VideoPlayerWidget
from ui.editor.editor_timeline_video import EditorTimelineVideoMixin


class _FrameStepTimeline:
    def __init__(self, sec=1.0):
        self.canvas = SimpleNamespace(playhead_sec=sec, _active_clip_idx=0)
        self.playhead_calls = []
        self.center_calls = []

    def set_playhead(self, sec):
        self.canvas.playhead_sec = sec
        self.playhead_calls.append(sec)

    def center_to_sec(self, sec, smooth=False):
        self.center_calls.append((sec, smooth))


class _FrameStepVideo:
    def __init__(self, path):
        self._current_source_path = path
        self.frame_seek_calls = []
        self.seek_direct_calls = []

    def frame_step_seek(self, sec):
        self.frame_seek_calls.append(sec)

    def seek_direct(self, sec):
        self.seek_direct_calls.append(sec)


class _FrameStepEditor(EditorTimelineVideoMixin):
    def __init__(self, current_path="/tmp/current.mp4", ctx_path="/tmp/current.mp4"):
        self.timeline = _FrameStepTimeline(sec=1.0)
        self.video_player = _FrameStepVideo(current_path)
        self.video_fps = 25.0
        self._active_seg_start = None
        self.applied_contexts = []
        self.ctx_path = ctx_path

    def _resolve_active_context(self, global_sec=None, clip_idx=None):
        return {
            "clip_file": self.ctx_path,
            "clip_idx": 0,
            "global_sec": float(global_sec),
            "local_sec": float(global_sec),
            "local_segments": [],
        }

    def _apply_active_context(self, ctx, autoplay=False, show_thumbnail=True):
        self.applied_contexts.append((ctx, autoplay, show_thumbnail))

    def _get_current_segments(self):
        return []


class _FrameStepOwner(QWidget):
    def __init__(self):
        super().__init__()
        self.calls = []

    def _on_step_frame(self, step):
        self.calls.append(int(step))


class _ExternalLikePlayer(QObject):
    durationChanged = pyqtSignal(int)
    mediaStatusChanged = pyqtSignal(object)

    backend_name = "external-test"
    uses_qt_audio = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = QUrl()
        self._video_widget = None

    def create_video_widget(self, parent=None):
        widget = QWidget(parent)
        widget.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self._video_widget = widget
        return widget

    def setVideoOutput(self, _output):
        return

    def setAudioOutput(self, _output):
        return

    def source(self):
        return self._source

    def setSource(self, source=None):
        self._source = source if isinstance(source, QUrl) else QUrl()

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


class VideoPlayerWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_video_backend_auto_stays_qt_under_tests(self):
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}, clear=True):
            choice = choose_video_backend("auto")

        self.assertEqual(choice.name, "qt")
        self.assertEqual(choice.reason, "test_or_offscreen_safe")

    def test_video_backend_auto_skips_embedded_mpv_without_safety_gate(self):
        with patch.dict(os.environ, {"AI_SUBTITLE_VIDEO_BACKEND": "auto"}, clear=True), \
             patch("ui.editor.video_playback_backend._running_under_pytest", return_value=False), \
             patch("ui.editor.video_playback_backend._offscreen_qt", return_value=False), \
             patch("ui.editor.video_playback_backend._embedded_mpv_enabled", return_value=False), \
             patch("ui.editor.video_playback_backend._mpv_available", return_value=True), \
             patch("ui.editor.video_playback_backend._vlc_available", return_value=False):
            choice = choose_video_backend()

        self.assertEqual(choice.name, "qt")
        self.assertEqual(choice.reason, "embedded_mpv_disabled")

    def test_video_backend_prefers_mpv_when_explicitly_enabled(self):
        with patch.dict(
            os.environ,
            {"AI_SUBTITLE_VIDEO_BACKEND": "auto", "AI_SUBTITLE_ENABLE_EMBEDDED_MPV": "1"},
            clear=True,
        ), \
             patch("ui.editor.video_playback_backend._running_under_pytest", return_value=False), \
             patch("ui.editor.video_playback_backend._offscreen_qt", return_value=False), \
             patch("ui.editor.video_playback_backend._mpv_available", return_value=True), \
             patch("ui.editor.video_playback_backend._vlc_available", return_value=True):
            choice = choose_video_backend()

        self.assertEqual(choice.name, "mpv")
        self.assertEqual(choice.reason, "preferred_lightweight_simple_backend")

    def test_video_backend_uses_qt_when_mpv_is_unavailable(self):
        with patch.dict(os.environ, {"AI_SUBTITLE_VIDEO_BACKEND": "auto"}, clear=True), \
             patch("ui.editor.video_playback_backend._running_under_pytest", return_value=False), \
             patch("ui.editor.video_playback_backend._offscreen_qt", return_value=False), \
             patch("ui.editor.video_playback_backend._mpv_available", return_value=False), \
             patch("ui.editor.video_playback_backend._vlc_available", return_value=True):
            choice = choose_video_backend()

        self.assertEqual(choice.name, "qt")
        self.assertEqual(choice.reason, "qt_simple_fallback")

    def test_video_backend_explicit_vlc_still_works(self):
        with patch.dict(os.environ, {"AI_SUBTITLE_VIDEO_BACKEND": "vlc"}, clear=True), \
             patch("ui.editor.video_playback_backend._running_under_pytest", return_value=False), \
             patch("ui.editor.video_playback_backend._offscreen_qt", return_value=False), \
             patch("ui.editor.video_playback_backend._vlc_available", return_value=True):
            choice = choose_video_backend()

        self.assertEqual(choice.name, "vlc")
        self.assertEqual(choice.reason, "libvlc_fallback")

    def test_video_backend_can_be_forced_by_render_settings(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch("ui.editor.video_playback_backend._settings_requested_video_backend", return_value="qt"), \
             patch("ui.editor.video_playback_backend._running_under_pytest", return_value=False), \
             patch("ui.editor.video_playback_backend._offscreen_qt", return_value=False), \
             patch("ui.editor.video_playback_backend._embedded_mpv_enabled", return_value=True), \
             patch("ui.editor.video_playback_backend._mpv_available", return_value=True), \
             patch("ui.editor.video_playback_backend._vlc_available", return_value=True):
            choice = choose_video_backend()

        self.assertEqual(choice.name, "qt")
        self.assertEqual(choice.reason, "forced")

    def test_external_video_backend_exposes_qt_playback_state_alias(self):
        class _DummyExternalBackend(_BaseExternalBackend):
            def __init__(self):
                super().__init__()
                self._playing = False

            def _load_source(self, _path):
                return

            def _play(self):
                self._playing = True

            def _pause(self):
                self._playing = False

            def _stop(self):
                self._playing = False

            def _is_playing(self):
                return self._playing

            def _position_ms(self):
                return 0

            def _set_position_ms(self, _position_ms):
                return

            def _duration(self):
                return 0

        backend = _DummyExternalBackend()
        try:
            self.assertIs(backend.PlaybackState, QMediaPlayer.PlaybackState)
            self.assertEqual(backend.playbackState(), backend.PlaybackState.PausedState)
            backend.play()
            self.assertEqual(backend.playbackState(), backend.PlaybackState.PlayingState)
        finally:
            backend.stop()
            backend.deleteLater()

    def test_frame_step_buttons_emit_single_frame_direction(self):
        widget = VideoPlayerWidget()
        emitted = []
        try:
            widget.frame_step_requested.connect(emitted.append)

            widget.btn_prev_frame.click()
            widget.btn_next_frame.click()

            self.assertEqual(emitted, [-1, 1])
            self.assertEqual(widget.btn_prev_frame.text(), "<")
            self.assertEqual(widget.btn_next_frame.text(), ">")
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_frame_step_button_prefers_direct_owner_handler_for_fast_response(self):
        owner = _FrameStepOwner()
        widget = VideoPlayerWidget(owner)
        emitted = []
        try:
            widget.frame_step_requested.connect(emitted.append)

            widget.btn_next_frame.click()

            self.assertEqual(owner.calls, [1])
            self.assertEqual(emitted, [])
        finally:
            widget.close()
            widget.deleteLater()
            owner.close()
            owner.deleteLater()
            self.app.processEvents()

    def test_play_button_tooltip_includes_editor_and_canvas_shortcuts(self):
        widget = VideoPlayerWidget()
        try:
            tooltip = widget.btn_play.toolTip()

            self.assertIn("Shift", tooltip)
            self.assertIn("Space", tooltip)
            self.assertIn("Tab", tooltip)
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_preview_starts_hevc_proxy_build_and_uses_original_until_ready(self):
        widget = VideoPlayerWidget()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                src = os.path.join(tmp, "sample.mp4")
                with open(src, "wb") as f:
                    f.write(b"video")

                proc = Mock()
                proc.poll.return_value = None
                with patch.object(widget, "_preview_proxy_enabled", return_value=True), \
                     patch("ui.editor.video_player_widget.subprocess.Popen", return_value=proc) as popen:
                    playback_path = widget._playback_path_for(src)

                self.assertEqual(playback_path, src)
                self.assertEqual(widget._proxy_playback_path, src)
                popen.assert_called_once()
                command = popen.call_args.args[0]
                self.assertIn("-c:v", command)
                self.assertIn(command[command.index("-c:v") + 1], {"hevc_videotoolbox", "libx265"})
                self.assertIn("force_original_aspect_ratio=decrease", " ".join(command))
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_preview_proxy_cache_is_invalidated_when_same_named_file_changes(self):
        widget = VideoPlayerWidget()
        try:
            with tempfile.TemporaryDirectory() as tmp, patch.object(config, "DATASET_DIR", tmp):
                src = os.path.join(tmp, "same_name.mp4")
                with open(src, "wb") as f:
                    f.write(b"old forty six minute proxy source" * 4096)

                stale_proxy = widget._proxy_path_for(src)
                os.makedirs(os.path.dirname(stale_proxy), exist_ok=True)
                with open(stale_proxy, "wb") as f:
                    f.write(b"old proxy")

                with open(src, "wb") as f:
                    f.write(b"new twenty four minute proxy source" * 2048)

                fresh_proxy = widget._proxy_path_for(src)
                with patch.object(widget, "_preview_proxy_enabled", return_value=True), \
                     patch.object(widget, "_start_proxy_build") as start_proxy_build:
                    playback_path = widget._playback_path_for(src)

                self.assertNotEqual(fresh_proxy, stale_proxy)
                self.assertEqual(playback_path, src)
                start_proxy_build.assert_called_once_with(src, fresh_proxy)
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_high_resolution_preview_waits_for_720p_proxy(self):
        widget = VideoPlayerWidget()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                src = os.path.join(tmp, "sample_4k.mp4")
                with open(src, "wb") as f:
                    f.write(b"video")

                widget._source_width = 3840
                widget._source_height = 2160
                with patch.object(widget, "_preview_proxy_enabled", return_value=True), \
                     patch.object(widget, "_wait_for_preview_proxy_enabled", return_value=True), \
                     patch.object(widget, "_start_proxy_build") as start_proxy_build:
                    playback_path = widget._playback_path_for(src)

                self.assertEqual(playback_path, "")
                self.assertFalse(widget._source_ready)
                start_proxy_build.assert_called_once()
                self.assertIn("720p", widget.info_label.text())
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_high_resolution_preview_uses_original_by_default_while_proxy_builds(self):
        widget = VideoPlayerWidget()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                src = os.path.join(tmp, "sample_4k.mp4")
                with open(src, "wb") as f:
                    f.write(b"video")

                widget._source_width = 3840
                widget._source_height = 2160
                with patch.object(widget, "_preview_proxy_enabled", return_value=True), \
                     patch.object(widget, "_start_proxy_build") as start_proxy_build:
                    playback_path = widget._playback_path_for(src)

                self.assertEqual(playback_path, src)
                self.assertTrue(widget._source_ready)
                self.assertEqual(widget._proxy_playback_path, src)
                start_proxy_build.assert_called_once()
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_zero_duration_event_preserves_probed_media_duration(self):
        widget = VideoPlayerWidget()
        try:
            widget._rebuild_frame_time_map(duration=1450.3, fps=59.94)

            widget._on_duration_changed(0)

            self.assertAlmostEqual(widget.total_time, 1450.3, places=3)
            self.assertGreater(widget.frame_time_map.total_frames, 0)
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_preview_proxy_is_default_on_without_setting(self):
        widget = VideoPlayerWidget()
        try:
            with tempfile.TemporaryDirectory() as tmp, patch.object(config, "DATASET_DIR", tmp):
                self.assertTrue(widget._legacy_preview_proxy_enabled())
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_external_backend_disables_preview_proxy_by_default(self):
        class _PreviewExternalBackend(_BaseExternalBackend):
            backend_name = "mpv"

            def __init__(self):
                super().__init__()
                self._playing = False

            def _load_source(self, _path):
                return

            def _play(self):
                self._playing = True

            def _pause(self):
                self._playing = False

            def _stop(self):
                self._playing = False

            def _is_playing(self):
                return self._playing

            def _position_ms(self):
                return 0

            def _set_position_ms(self, _position_ms):
                return

            def _duration(self):
                return 0

        with patch("ui.editor.video_player_widget.create_video_backend", return_value=_PreviewExternalBackend()):
            widget = VideoPlayerWidget()
        try:
            with tempfile.TemporaryDirectory() as tmp, patch.object(config, "DATASET_DIR", tmp):
                self.assertFalse(widget._preview_proxy_enabled())
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_preview_display_rect_uses_full_default_16_9_bounds(self):
        widget = VideoPlayerWidget()
        try:
            widget._display_aspect = 16 / 9
            rect = widget._displayed_video_rect(SimpleNamespace(width=lambda: 1920, height=lambda: 1080))
            self.assertEqual(rect.width(), 1920)
            self.assertEqual(rect.height(), 1080)
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_video_surface_uses_contain_aspect_ratio_to_avoid_preview_crop(self):
        view = VideoSurfaceView()
        try:
            self.assertEqual(view.video_item.aspectRatioMode(), Qt.AspectRatioMode.KeepAspectRatio)
        finally:
            view.close()
            view.deleteLater()
            self.app.processEvents()

    def test_video_surface_resize_preserves_parent_display_rect(self):
        view = VideoSurfaceView()
        try:
            view.resize(640, 360)
            self.app.processEvents()
            explicit = QRectF(20, 30, 320, 180)
            view.set_video_display_rect(explicit)

            view.resize(800, 450)
            self.app.processEvents()

            self.assertEqual(view.video_item.pos().x(), explicit.left())
            self.assertEqual(view.video_item.pos().y(), explicit.top())
            self.assertEqual(view.video_item.size().width(), explicit.width())
            self.assertEqual(view.video_item.size().height(), explicit.height())
        finally:
            view.close()
            view.deleteLater()
            self.app.processEvents()

    def test_qml_video_subtitle_overlay_is_opt_in_to_avoid_black_metal_composite(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch("ui.editor.video_overlay_widgets.scenegraph_enabled", return_value=True):
            self.assertIsNone(SubtitleQuickOverlay.create())

    def test_source_name_badge_lives_on_control_bar_right(self):
        widget = VideoPlayerWidget()
        try:
            widget.video_container.resize(640, 360)
            widget._source_aspect = 16 / 9
            path = "/tmp/DJI_20260504010101_very_long_camera_clip_name.MP4"

            widget._set_source_name_badge(path)
            widget._layout_video_overlay()

            label = widget.source_name_label
            self.assertFalse(label.isHidden())
            self.assertEqual(label.toolTip(), os.path.basename(path))
            self.assertEqual(label.text(), os.path.basename(path))
            self.assertFalse(label.wordWrap())
            self.assertIn("border-radius: 9px", label.styleSheet())
            self.assertIs(label.parentWidget(), widget.status_info_container)
            self.assertIs(label.parentWidget(), widget.info_label.parentWidget())
            control_layout = label.parentWidget().layout()
            self.assertGreater(control_layout.indexOf(label), control_layout.indexOf(widget.info_label))
            self.assertEqual(control_layout.stretch(0), 1)
            self.assertEqual(control_layout.stretch(1), 1)
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_source_meta_badge_shows_probe_details_in_left_half(self):
        widget = VideoPlayerWidget()
        try:
            with tempfile.NamedTemporaryFile(suffix=".MP4") as f, \
                 patch("core.media_info.probe_media", return_value={
                     "duration": 24.0,
                     "fps": 60000.0 / 1001.0,
                     "width": 3840,
                     "height": 2160,
                     "bit_rate": 42100000,
                     "pix_fmt": "yuv420p10le",
                     "color_space": "bt709",
                     "color_primaries": "bt709",
                 }), \
                 patch.object(widget, "_playback_path_for", return_value=f.name), \
                 patch.object(widget, "_set_media_source_if_needed", return_value=False), \
                 patch.object(widget, "_extract_and_show_thumbnail"):
                widget.load(f.name, [])

            info_text = widget.info_label.text()
            self.assertIn("3840x2160", info_text)
            self.assertIn("59.94fps", info_text)
            self.assertIn("yuv420p10le", info_text)
            self.assertIn("bt709", info_text)
            self.assertIn("42.1Mbps", info_text)
            self.assertEqual(widget.source_name_label.text(), os.path.basename(f.name))
            state = widget._quick_control_bar_state()
            self.assertEqual(state["infoText"], info_text)
            self.assertEqual(state["sourceNameText"], os.path.basename(f.name))
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_deferred_probe_replaces_loading_text_with_source_metadata(self):
        widget = VideoPlayerWidget()
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp4") as f, \
                 patch.object(widget, "_playback_path_for", return_value=f.name), \
                 patch.object(widget, "_set_media_source_if_needed", return_value=False), \
                 patch.object(widget, "_schedule_initial_thumbnail_prepare"):
                widget.load(f.name, [], defer_probe=True)

                self.assertIn("불러오는 중", widget.info_label.text())

                widget.apply_source_media_probe(f.name, {
                    "duration": 12.0,
                    "fps": 24.0,
                    "width": 1920,
                    "height": 1080,
                    "bit_rate": 12000000,
                    "pix_fmt": "yuv420p",
                    "color_space": "bt709",
                })

            self.assertIn("1920x1080", widget.info_label.text())
            self.assertIn("24fps", widget.info_label.text())
            self.assertNotIn("불러오는 중", widget.info_label.text())
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_frame_count_label_shows_current_and_total_frames(self):
        widget = VideoPlayerWidget()
        try:
            self.assertFalse(widget.frame_count_label.isHidden())
            self.assertEqual(widget.frame_count_label.text(), "F 0 / 0")
            widget.current_time = 2.0
            widget._rebuild_frame_time_map(duration=10.0, fps=25.0)
            control_layout = widget.frame_count_label.parentWidget().layout()

            self.assertFalse(widget.frame_count_label.isHidden())
            self.assertEqual(widget.frame_count_label.text(), "F 50 / 250")
            self.assertGreater(control_layout.indexOf(widget.frame_count_label), control_layout.indexOf(widget.time_label))
            self.assertLess(control_layout.indexOf(widget.frame_count_label), control_layout.indexOf(widget.status_info_container))

            widget._apply_seek_state(4.0)

            self.assertEqual(widget.frame_count_label.text(), "F 100 / 250")
            state = widget._quick_control_bar_state()
            self.assertEqual(state["frameText"], "F 100 / 250")
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_subtitle_overlay_uses_display_time_override(self):
        widget = VideoPlayerWidget()
        try:
            widget.set_context_segments([
                {"start": 0.0, "end": 1.5, "text": "현재 자막"},
                {"start": 1.5, "end": 3.0, "text": "다음 자막"},
            ])

            widget.current_time = 1.8
            widget.set_subtitle_display_time(1.2)
            self.assertEqual(widget._last_sub, "현재 자막")
            self.assertEqual(widget.sub_label.text(), "현재 자막")
            self.assertEqual(widget.video_widget.subtitle_item.text(), "현재 자막")

            widget.set_subtitle_display_time(1.8)
            self.assertEqual(widget._last_sub, "다음 자막")
            self.assertEqual(widget.sub_label.text(), "다음 자막")
            self.assertEqual(widget.video_widget.subtitle_item.text(), "다음 자막")
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_external_video_backend_hosts_subtitle_overlay_on_video_widget(self):
        with patch("ui.editor.video_player_widget.create_video_backend", return_value=_ExternalLikePlayer()):
            widget = VideoPlayerWidget()
        try:
            widget.resize(640, 360)
            widget.video_container.resize(640, 360)
            widget._source_aspect = 16 / 9
            widget._display_aspect = 16 / 9
            widget._layout_video_overlay()
            widget.set_context_segments([
                {"start": 0.0, "end": 2.0, "text": "외부 백엔드 자막"},
            ])
            widget.set_subtitle_display_time(0.5)

            self.assertIsNone(widget._scene_subtitle_item())
            self.assertIs(widget.sub_label.parentWidget(), widget.video_widget)
            self.assertFalse(widget.sub_label.isHidden())
            self.assertEqual(widget.sub_label.text(), "외부 백엔드 자막")
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_external_backend_can_autoplay_once_loaded_event_arrives(self):
        class _AutoPlayExternalBackend(_BaseExternalBackend):
            def __init__(self):
                super().__init__()
                self._playing = False

            def _load_source(self, _path):
                return

            def _play(self):
                self._playing = True

            def _pause(self):
                self._playing = False

            def _stop(self):
                self._playing = False

            def _is_playing(self):
                return self._playing

            def _position_ms(self):
                return 0

            def _set_position_ms(self, _position_ms):
                return

            def _duration(self):
                return 1200

        backend = _AutoPlayExternalBackend()
        with patch("ui.editor.video_player_widget.create_video_backend", return_value=backend):
            widget = VideoPlayerWidget()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                media_path = os.path.join(tmp, "sample.mp4")
                with open(media_path, "wb") as f:
                    f.write(b"video")

                widget.load(media_path, defer_probe=True)
                widget.toggle_play()
                self.app.processEvents()

                self.assertEqual(backend.playbackState(), backend.PlaybackState.PlayingState)
                self.assertTrue(widget._video_surface_primed)
        finally:
            widget.close()
            widget.deleteLater()
            backend.stop()
            backend.deleteLater()
            self.app.processEvents()

    def test_scene_subtitle_overlay_loads_export_style_on_first_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "user_settings.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {"export_dialog": {"res": "4K (3840px)", "size": "24", "align": "가운데"}},
                    f,
                )

            with patch.object(config, "DATASET_DIR", tmp):
                widget = VideoPlayerWidget()
                try:
                    style = widget.video_widget.subtitle_item._style
                    self.assertEqual(style.get("size"), "24")
                    self.assertEqual(style.get("res"), "4K (3840px)")
                finally:
                    widget.close()
                    widget.deleteLater()
                    self.app.processEvents()

    def test_repeated_same_subtitle_time_does_not_update_scene_overlay(self):
        widget = VideoPlayerWidget()
        try:
            widget.set_context_segments([
                {"start": 0.0, "end": 2.0, "text": "현재 자막"},
            ])
            widget.set_subtitle_display_time(0.5)

            with patch.object(widget.video_widget.subtitle_item, "set_text", wraps=widget.video_widget.subtitle_item.set_text) as set_text, \
                 patch.object(widget.sub_label, "setText", wraps=widget.sub_label.setText) as set_label_text:
                widget.set_subtitle_display_time(0.6)

            set_text.assert_not_called()
            set_label_text.assert_not_called()
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_same_subtitle_time_reapplies_hidden_scene_overlay(self):
        widget = VideoPlayerWidget()
        try:
            widget.set_context_segments([
                {"start": 0.0, "end": 2.0, "text": "현재 자막"},
            ])
            widget.set_subtitle_display_time(0.5)
            widget.video_widget.subtitle_item.setVisible(False)

            widget.set_subtitle_display_time(0.6)

            self.assertTrue(widget.video_widget.subtitle_item.isVisible())
            self.assertEqual(widget.video_widget.subtitle_item.text(), "현재 자막")
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_playing_ui_tick_does_not_poll_subtitle_provider(self):
        widget = VideoPlayerWidget()
        provider = Mock(return_value=[{"start": 0.0, "end": 2.0, "text": "현재 자막"}])
        try:
            widget.set_subtitle_provider(provider)
            provider.reset_mock()
            widget._last_provider_refresh_at = 0.0

            with patch.object(widget.media_player, "playbackState", return_value=QMediaPlayer.PlaybackState.PlayingState), \
                 patch.object(widget, "current_playback_frame_time", return_value=(0, 0.0)):
                widget._ui_tick()

            provider.assert_not_called()
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_subtitle_display_time_refreshes_provider_when_playhead_leaves_context(self):
        widget = VideoPlayerWidget()
        early_context = [{"start": 0.0, "end": 1.0, "text": "초반 자막"}]
        current_context = [{"start": 117.0, "end": 118.0, "text": "현재 자막"}]
        use_current_context = False

        def provider():
            return current_context if use_current_context else early_context

        provider_mock = Mock(side_effect=provider)
        try:
            widget.set_subtitle_provider(provider_mock)
            self.assertEqual(widget._find_subtitle_at(117.2), "")
            provider_mock.reset_mock()
            use_current_context = True

            widget.set_subtitle_display_time(117.2)

            provider_mock.assert_called_once()
            self.assertEqual(widget._last_sub, "현재 자막")
            self.assertEqual(widget.video_widget.subtitle_item.text(), "현재 자막")
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_provider_refresh_rehashes_same_list_reference_to_catch_in_place_mutation(self):
        widget = VideoPlayerWidget()
        shared = [{"start": 0.0, "end": 2.0, "text": "현재 자막"}]
        provider = Mock(return_value=shared)
        try:
            widget.set_subtitle_provider(provider)
            widget.set_subtitle_display_time(0.5)
            provider.reset_mock()
            widget._last_provider_refresh_at = 0.0
            shared[0]["text"] = "수정 자막"

            with patch.object(widget, "_normalized_segments_context", wraps=widget._normalized_segments_context) as signature_mock:
                widget._provider_refresh_requested = True
                widget._refresh_provider_segments(force=False)

            provider.assert_called_once()
            signature_mock.assert_called()
            self.assertEqual(widget._last_sub, "수정 자막")
            self.assertEqual(widget.sub_label.text(), "수정 자막")
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_provider_refresh_skips_full_context_build_when_signature_is_unchanged(self):
        widget = VideoPlayerWidget()
        shared = [{"start": 0.0, "end": 2.0, "text": "현재 자막"}]
        provider = Mock(return_value=shared)
        try:
            widget.set_subtitle_provider(provider)
            provider.reset_mock()
            widget._last_provider_refresh_at = 0.0

            with patch.object(widget, "_segments_signature_fast", wraps=widget._segments_signature_fast) as fast_signature, \
                 patch.object(widget, "_normalized_segments_context", side_effect=AssertionError("unchanged provider should not rebuild subtitle context")):
                widget._provider_refresh_requested = True
                widget._refresh_provider_segments(force=False)

            provider.assert_called_once()
            fast_signature.assert_called_once_with(shared)
            self.assertFalse(widget._provider_refresh_requested)
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_context_segments_refreshes_when_same_list_reference_is_mutated(self):
        widget = VideoPlayerWidget()
        shared = [{"start": 0.0, "end": 2.0, "text": "현재 자막"}]
        try:
            widget.set_context_segments(shared)
            widget.set_subtitle_display_time(0.5)

            shared[0]["text"] = "수정 자막"
            widget.refresh_subtitle_context(shared)

            self.assertEqual(widget._last_sub, "수정 자막")
            self.assertEqual(widget.sub_label.text(), "수정 자막")
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_context_refresh_skips_full_context_build_when_signature_is_unchanged(self):
        widget = VideoPlayerWidget()
        shared = [{"start": 0.0, "end": 2.0, "text": "현재 자막"}]
        try:
            widget.set_context_segments(shared)
            widget.set_subtitle_display_time(0.5)

            with patch.object(widget, "_segments_signature_fast", wraps=widget._segments_signature_fast) as fast_signature, \
                 patch.object(widget, "_normalized_segments_context", side_effect=AssertionError("unchanged context should not rebuild subtitle rows")):
                widget.refresh_subtitle_context(shared)

            fast_signature.assert_called_once_with(shared)
            self.assertEqual(widget._last_sub, "현재 자막")
            self.assertEqual(widget.sub_label.text(), "현재 자막")
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_set_segments_skips_sort_for_already_sorted_large_context(self):
        widget = VideoPlayerWidget()
        segments = [
            {"start": float(i), "end": float(i) + 0.8, "text": f"자막 {i}"}
            for i in range(1000)
        ]
        try:
            with patch("builtins.sorted", side_effect=AssertionError("sorted context should not be resorted")):
                changed = widget._set_segments(segments)

            self.assertTrue(changed)
            self.assertEqual(len(widget.segments), 1000)
            self.assertEqual(widget._subtitle_starts[500], 500.0)
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_set_segments_reuses_prebuilt_parallel_arrays(self):
        widget = VideoPlayerWidget()
        normalized = [
            {"start": 0.0, "end": 1.0, "text": "첫 자막"},
            {"start": 1.0, "end": 2.0, "text": "둘째 자막"},
        ]
        starts = [0.0, 1.0]
        ends = [1.0, 2.0]
        texts = ["첫 자막", "둘째 자막"]
        try:
            changed = widget._set_segments(
                normalized,
                normalized=normalized,
                signature="prefetched-signature",
                sorted_ok=True,
                starts=starts,
                ends=ends,
                texts=texts,
            )

            self.assertTrue(changed)
            self.assertIs(widget.segments, normalized)
            self.assertIs(widget._subtitle_starts, starts)
            self.assertIs(widget._subtitle_ends, ends)
            self.assertIs(widget._subtitle_texts, texts)
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_video_subtitle_context_keeps_lightweight_overlay_rows(self):
        widget = VideoPlayerWidget()
        heavy_payload = {"confidence_label": "green", "history": ["x" * 1024]}
        segments = [
            {
                "start": 0.0,
                "end": 2.0,
                "text": "현재 자막",
                "speaker": "SPEAKER_00",
                "quality": heavy_payload,
                "stt_candidates": [{"text": "후보", "score": 0.9}],
            }
        ]
        try:
            changed = widget._set_segments(segments)

            self.assertTrue(changed)
            self.assertEqual(widget.segments, [{"start": 0.0, "end": 2.0, "text": "현재 자막"}])
            self.assertNotIn("quality", widget.segments[0])
            self.assertNotIn("stt_candidates", widget.segments[0])
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_subtitle_lookup_uses_parallel_arrays_during_playback(self):
        class GuardedSegments(list):
            def __getitem__(self, index):
                raise AssertionError("subtitle playback lookup should not read segment dicts")

        widget = VideoPlayerWidget()
        try:
            widget._set_segments([
                {"start": 0.0, "end": 1.0, "text": "첫 자막"},
                {"start": 1.0, "end": 2.0, "text": "둘째 자막"},
            ])
            widget.segments = GuardedSegments(widget.segments)

            self.assertEqual(widget._find_subtitle_at(1.25), "둘째 자막")
            self.assertEqual(widget._find_subtitle_at(1.50), "둘째 자막")
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_toggle_play_rewinds_to_last_playable_frame_near_end(self):
        widget = VideoPlayerWidget()
        try:
            widget.total_time = 10.0
            widget.set_frame_rate(25.0)
            widget.current_time = 10.0
            widget._media_source_loaded = True

            with patch.object(widget, "_ensure_media_source_loaded", return_value=True), \
                 patch.object(widget, "_refresh_provider_segments"), \
                 patch.object(widget, "_hide_thumbnail"), \
                 patch.object(widget.media_player, "playbackState", return_value=QMediaPlayer.PlaybackState.StoppedState), \
                 patch.object(widget.media_player, "setPosition") as set_position, \
                 patch.object(widget.media_player, "play") as play_mock, \
                 patch.object(widget, "_ensure_audio_outputs"):
                widget.toggle_play()

            set_position.assert_called_once_with(9960)
            play_mock.assert_called_once()
            self.assertEqual(widget.current_frame, 249)
            self.assertAlmostEqual(widget.current_time, 9.96, places=2)
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_seek_direct_uses_frame_position_mapping(self):
        widget = VideoPlayerWidget()
        try:
            widget._rebuild_frame_time_map(duration=10.0, fps=24.0)
            widget._media_source_loaded = True

            with patch.object(widget.media_player, "setPosition") as set_position, \
                 patch.object(widget, "_refresh_provider_segments"):
                widget.seek_direct(1.041)

            self.assertEqual(widget.current_frame, 24)
            self.assertAlmostEqual(widget.current_time, 1.0, places=6)
            set_position.assert_called_once_with(1000)
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_initial_paused_preview_seek_keeps_thumbnail_until_video_surface_is_primed(self):
        widget = VideoPlayerWidget()
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
                widget._current_source_path = f.name
                widget._rebuild_frame_time_map(duration=10.0, fps=30.0)
                widget._media_source_loaded = True
                widget._video_surface_primed = False

                with patch.object(widget.media_player, "setPosition") as set_position, \
                     patch.object(widget, "_hide_thumbnail") as hide_thumbnail, \
                     patch.object(widget, "show_cached_thumbnail_at", return_value=True) as show_thumb:
                    widget.preview_seek(3.0)

                set_position.assert_called_once_with(3000)
                hide_thumbnail.assert_not_called()
                show_thumb.assert_called_once_with(f.name, 3.0, width=640)
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_primed_preview_seek_uses_video_surface_instead_of_thumbnail(self):
        widget = VideoPlayerWidget()
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
                widget._current_source_path = f.name
                widget._rebuild_frame_time_map(duration=10.0, fps=30.0)
                widget._media_source_loaded = True
                widget._video_surface_primed = True

                with patch.object(widget.media_player, "setPosition") as set_position, \
                     patch.object(widget, "_hide_thumbnail") as hide_thumbnail, \
                     patch.object(widget, "show_cached_thumbnail_at", return_value=True) as show_thumb:
                    widget.preview_seek(3.0)

                set_position.assert_called_once_with(3000)
                hide_thumbnail.assert_called_once()
                show_thumb.assert_not_called()
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_video_load_builds_frame_time_map(self):
        widget = VideoPlayerWidget()
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp4") as f, \
                 patch("core.media_info.probe_media", return_value={
                     "duration": 2.0,
                     "fps": 24.0,
                     "width": 1280,
                     "height": 720,
                 }), \
                 patch.object(widget, "_playback_path_for", return_value=f.name), \
                 patch.object(widget, "_set_media_source_if_needed", return_value=False), \
                 patch.object(widget, "_extract_and_show_thumbnail"):
                widget.load(f.name, [])

            self.assertEqual(widget.frame_time_map.total_frames, 48)
            self.assertEqual(widget.frame_rate, 24.0)
            self.assertAlmostEqual(widget.snap_sec_to_frame(1.01), 1.0, places=6)
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_video_load_with_deferred_probe_avoids_sync_probe_and_thumbnail_extract(self):
        widget = VideoPlayerWidget()
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp4") as f, \
                 patch("core.media_info.probe_media") as probe_media, \
                 patch.object(widget, "_playback_path_for", return_value=f.name), \
                 patch.object(widget, "_set_media_source_if_needed", return_value=False), \
                 patch.object(widget, "_extract_and_show_thumbnail") as extract_thumb, \
                 patch.object(widget, "_schedule_initial_thumbnail_prepare") as schedule_thumb:
                widget.load(f.name, [], defer_probe=True)

            probe_media.assert_not_called()
            extract_thumb.assert_not_called()
            schedule_thumb.assert_called_once_with(f.name, 0.0, width=640)
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_current_playback_time_uses_mapped_frame(self):
        widget = VideoPlayerWidget()
        try:
            widget._rebuild_frame_time_map(duration=10.0, fps=24.0)
            widget.media_player = SimpleNamespace(position=lambda: 1041, stop=lambda: None)

            frame, sec = widget.current_playback_frame_time()

            self.assertEqual(frame, 25)
            self.assertAlmostEqual(sec, 25.0 / 24.0, places=6)
            self.assertEqual(widget.current_frame, 25)
            self.assertAlmostEqual(widget.current_time, 25.0 / 24.0, places=6)
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_frame_step_uses_fast_seek_without_reloading_same_video(self):
        editor = _FrameStepEditor()

        editor._on_step_frame(1)

        self.assertEqual(editor.applied_contexts, [])
        self.assertEqual(len(editor.video_player.frame_seek_calls), 1)
        self.assertAlmostEqual(editor.video_player.frame_seek_calls[0], 1.04, places=4)
        self.assertEqual(editor.video_player.seek_direct_calls, [])

    def test_frame_step_accepts_multi_frame_direction_for_keyboard_acceleration(self):
        editor = _FrameStepEditor()

        editor._on_step_frame(3)

        self.assertEqual(editor.applied_contexts, [])
        self.assertEqual(len(editor.video_player.frame_seek_calls), 1)
        self.assertAlmostEqual(editor.video_player.frame_seek_calls[0], 1.12, places=4)
        self.assertEqual(editor.video_player.seek_direct_calls, [])

    def test_frame_step_context_switch_suppresses_thumbnail_extraction(self):
        editor = _FrameStepEditor(current_path="/tmp/current.mp4", ctx_path="/tmp/next.mp4")

        editor._on_step_frame(1)

        self.assertEqual(len(editor.applied_contexts), 1)
        self.assertFalse(editor.applied_contexts[0][1])
        self.assertFalse(editor.applied_contexts[0][2])

    def test_frame_step_keeps_exact_indices_on_59_94fps_sources(self):
        fps = 60000.0 / 1001.0
        editor = _FrameStepEditor()
        editor.video_fps = fps
        editor.timeline.canvas.playhead_sec = frame_to_sec(312, fps)

        editor._on_step_frame(1)
        editor._on_step_frame(1)

        self.assertEqual(len(editor.video_player.frame_seek_calls), 2)
        self.assertAlmostEqual(editor.video_player.frame_seek_calls[0], frame_to_sec(313, fps), places=6)
        self.assertAlmostEqual(editor.video_player.frame_seek_calls[1], frame_to_sec(314, fps), places=6)
        self.assertEqual(editor._manual_frame_idx, 314)

    def test_video_widget_frame_step_seek_preserves_exact_59_94_frame_label(self):
        widget = VideoPlayerWidget()
        try:
            fps = 60000.0 / 1001.0
            widget._rebuild_frame_time_map(duration=20.0, fps=fps)

            widget.frame_step_seek(frame_to_sec(313, fps))

            self.assertEqual(widget.current_frame, 313)
            self.assertAlmostEqual(widget.current_time, frame_to_sec(313, fps), places=6)
            self.assertEqual(widget.frame_count_label.text(), f"F 313 / {widget.frame_time_map.total_frames}")
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_clip_context_waits_for_new_media_source_before_consuming_pending_seek(self):
        widget = VideoPlayerWidget()
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
                widget._current_source_path = "/tmp/clip_a.mp4"
                with patch.object(widget, "_is_video_file", return_value=False), \
                     patch.object(widget, "_playback_path_for", return_value=f.name), \
                     patch.object(widget, "_ensure_media_source_loaded", side_effect=[False, True]), \
                     patch.object(widget.media_player, "setPosition") as set_position, \
                     patch.object(widget, "toggle_play") as toggle_play:
                    widget.load_clip_context(
                        f.name,
                        segments=[{"start": 0.0, "end": 1.0, "text": "둘째 클립"}],
                        seek_sec=2.0,
                        autoplay=True,
                        show_thumbnail=False,
                    )

                    self.assertEqual(widget._pending_seek_sec, 2.0)
                    self.assertTrue(widget._pending_autoplay)
                    set_position.assert_not_called()
                    toggle_play.assert_not_called()

                    widget._apply_loaded_media_state()

                set_position.assert_called_with(2000)
                self.assertIsNone(widget._pending_seek_sec)
                self.assertFalse(widget._pending_autoplay)
                toggle_play.assert_called_once()
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
