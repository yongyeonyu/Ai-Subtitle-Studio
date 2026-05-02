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

import config
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

    def test_preview_uses_original_source_without_encoding_proxy(self):
        widget = VideoPlayerWidget()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                src = os.path.join(tmp, "sample.mp4")
                with open(src, "wb") as f:
                    f.write(b"video")

                with patch("ui.editor.video_player_widget.subprocess.Popen") as popen:
                    playback_path = widget._playback_path_for(src)

                self.assertEqual(playback_path, src)
                self.assertEqual(widget._proxy_playback_path, src)
                popen.assert_not_called()
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


if __name__ == "__main__":
    unittest.main()
