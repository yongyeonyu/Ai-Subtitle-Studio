# Version: 03.09.07
# Phase: PHASE2
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtMultimedia import QMediaPlayer

from core.runtime import config
from ui.editor.video_playback_backend import choose_video_backend
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


class VideoPlayerWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_video_backend_auto_stays_qt_under_tests(self):
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}, clear=True):
            choice = choose_video_backend("auto")

        self.assertEqual(choice.name, "qt")
        self.assertEqual(choice.reason, "test_or_offscreen_safe")

    def test_video_backend_prefers_mpv_when_available(self):
        with patch.dict(os.environ, {"AI_SUBTITLE_VIDEO_BACKEND": "auto"}, clear=True), \
             patch("ui.editor.video_playback_backend._running_under_pytest", return_value=False), \
             patch("ui.editor.video_playback_backend._offscreen_qt", return_value=False), \
             patch("ui.editor.video_playback_backend._mpv_available", return_value=True), \
             patch("ui.editor.video_playback_backend._vlc_available", return_value=True):
            choice = choose_video_backend()

        self.assertEqual(choice.name, "mpv")
        self.assertEqual(choice.reason, "preferred_lightweight_gpu_backend")

    def test_video_backend_uses_vlc_when_mpv_is_unavailable(self):
        with patch.dict(os.environ, {"AI_SUBTITLE_VIDEO_BACKEND": "auto"}, clear=True), \
             patch("ui.editor.video_playback_backend._running_under_pytest", return_value=False), \
             patch("ui.editor.video_playback_backend._offscreen_qt", return_value=False), \
             patch("ui.editor.video_playback_backend._mpv_available", return_value=False), \
             patch("ui.editor.video_playback_backend._vlc_available", return_value=True):
            choice = choose_video_backend()

        self.assertEqual(choice.name, "vlc")
        self.assertEqual(choice.reason, "libvlc_fallback")

    def test_video_backend_can_be_forced_by_render_settings(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch("ui.editor.video_playback_backend._settings_requested_video_backend", return_value="qt"), \
             patch("ui.editor.video_playback_backend._running_under_pytest", return_value=False), \
             patch("ui.editor.video_playback_backend._offscreen_qt", return_value=False), \
             patch("ui.editor.video_playback_backend._mpv_available", return_value=True), \
             patch("ui.editor.video_playback_backend._vlc_available", return_value=True):
            choice = choose_video_backend()

        self.assertEqual(choice.name, "qt")
        self.assertEqual(choice.reason, "forced")

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

    def test_preview_starts_hevc_proxy_build_and_uses_original_until_ready(self):
        widget = VideoPlayerWidget()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                src = os.path.join(tmp, "sample.mp4")
                with open(src, "wb") as f:
                    f.write(b"video")

                proc = Mock()
                proc.poll.return_value = None
                with patch("ui.editor.video_player_widget.subprocess.Popen", return_value=proc) as popen:
                    playback_path = widget._playback_path_for(src)

                self.assertEqual(playback_path, src)
                self.assertEqual(widget._proxy_playback_path, src)
                popen.assert_called_once()
                command = popen.call_args.args[0]
                self.assertIn("-c:v", command)
                self.assertIn(command[command.index("-c:v") + 1], {"hevc_videotoolbox", "libx265"})
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
                with patch.object(widget, "_start_proxy_build") as start_proxy_build:
                    playback_path = widget._playback_path_for(src)

                self.assertNotEqual(fresh_proxy, stale_proxy)
                self.assertEqual(playback_path, src)
                start_proxy_build.assert_called_once_with(src, fresh_proxy)
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_preview_display_rect_is_capped_to_720p(self):
        widget = VideoPlayerWidget()
        try:
            widget._source_aspect = 16 / 9
            rect = widget._displayed_video_rect(SimpleNamespace(width=lambda: 1920, height=lambda: 1080))
            self.assertLessEqual(rect.height(), 720)
            self.assertLessEqual(rect.width(), 1280)
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

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
            self.assertIn("background: transparent", label.styleSheet())
            self.assertIn("border: none", label.styleSheet())
            self.assertIsNot(label.parentWidget(), widget.video_container)
            self.assertIs(label.parentWidget(), widget.info_label.parentWidget())
            control_layout = label.parentWidget().layout()
            self.assertGreater(control_layout.indexOf(label), control_layout.indexOf(widget.info_label))
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

            with patch.object(widget, "_segments_signature", wraps=widget._segments_signature) as signature_mock:
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

    def test_current_playback_time_uses_mapped_frame(self):
        widget = VideoPlayerWidget()
        try:
            widget._rebuild_frame_time_map(duration=10.0, fps=24.0)
            widget.media_player = SimpleNamespace(position=lambda: 1041, stop=lambda: None)

            frame, sec = widget.current_playback_frame_time()

            self.assertEqual(frame, 24)
            self.assertAlmostEqual(sec, 1.0, places=6)
            self.assertEqual(widget.current_frame, 24)
            self.assertAlmostEqual(widget.current_time, 1.0, places=6)
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

    def test_frame_step_context_switch_suppresses_thumbnail_extraction(self):
        editor = _FrameStepEditor(current_path="/tmp/current.mp4", ctx_path="/tmp/next.mp4")

        editor._on_step_frame(1)

        self.assertEqual(len(editor.applied_contexts), 1)
        self.assertFalse(editor.applied_contexts[0][1])
        self.assertFalse(editor.applied_contexts[0][2])

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
