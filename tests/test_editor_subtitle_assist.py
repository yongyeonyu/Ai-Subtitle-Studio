import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.editor.editor_subtitle_assist import (
    EditorSubtitleAssistMixin,
    apply_netflix_subtitle_magnet,
    compute_subtitle_magnet_policy,
)
from ui.timeline.timeline_widget import TimelineWidget


class _RepeatAssistEditor(EditorSubtitleAssistMixin):
    def __init__(self):
        self.settings = {
            "sub_gap_break_sec": 1.5,
            "subtitle_lora_micro_merge_gap_sec": 1.8,
            "deep_sequence_bridge_gap_sec": 0.3,
        }
        self.media_path = ""
        self.timeline = SimpleNamespace(
            repeat_chk=SimpleNamespace(isChecked=lambda: True),
            set_active=Mock(),
            set_playhead=Mock(),
            center_to_sec=Mock(),
        )
        self.video_player = SimpleNamespace(
            pause_video=Mock(side_effect=self._pause_video),
            seek_direct=Mock(),
        )
        self._segments = [
            {"line": 0, "start": 0.0, "end": 1.0, "text": "첫 줄", "spk": "00"},
            {"line": 1, "start": 1.2, "end": 2.0, "text": "둘째 줄", "spk": "00"},
        ]
        self._active_seg_start = 0.0
        self._playing = False
        self.synced = []
        self.seek_calls = []
        self._init_subtitle_assist_state()

    def _pause_video(self):
        self._playing = False

    def _get_current_segments(self, force_rebuild: bool = False):
        return [dict(seg) for seg in self._segments]

    def _is_video_playing(self):
        return bool(self._playing)

    def _toggle_video_play(self):
        self._playing = not self._playing

    def _timeline_lock_edit_enabled(self):
        return False

    def _sync_cursor_to_seg(self, seg, ensure_visible=True, move_cursor=True, *, sync_playhead=True):
        self._active_seg_start = float(seg.get("start", 0.0) or 0.0)
        self.synced.append(self._active_seg_start)

    def _seek_global_exact(self, sec: float):
        self.seek_calls.append(float(sec))
        return False

    def _global_to_local_sec(self, sec: float) -> float:
        return float(sec)

    def _reset_playhead_smoothing(self, sec: float | None = None):
        self._last_smoothed = float(sec or 0.0)

    def _current_frame_fps(self) -> float:
        return 30.0


class _MagnetAssistEditor(EditorSubtitleAssistMixin):
    def __init__(self):
        self.settings = {
            "sub_gap_break_sec": 1.5,
            "subtitle_lora_micro_merge_gap_sec": 1.8,
            "deep_sequence_bridge_gap_sec": 0.3,
        }
        self.media_path = ""
        self.video_fps = 30.0
        self._segments = [
            {"line": 0, "start": 0.0, "end": 1.0, "text": "안녕", "spk": "00"},
            {"line": 1, "start": 1.6, "end": 2.4, "text": "하세요", "spk": "00"},
        ]
        self.timeline = SimpleNamespace(
            canvas=SimpleNamespace(
                boundary_times=[],
                scan_boundary_times=[],
                vad_segments=[],
                voice_activity_segments=[],
            ),
            set_active=Mock(),
        )
        self.status_lbl = SimpleNamespace(setText=Mock())
        self._undo_mgr = SimpleNamespace(push_immediate=Mock())
        self._active_seg_start = 0.0
        self._autosave_requires_manual_save = False
        self.loaded_segments = None
        self.loaded_kwargs = None
        self.dirty_marked = False

    def _get_current_segments(self, force_rebuild: bool = False):
        return [dict(seg) for seg in self._segments]

    def apply_loaded_canvas_state(self, segments, **kwargs):
        self.loaded_segments = [dict(seg) for seg in list(segments or [])]
        self.loaded_kwargs = dict(kwargs)

    def _mark_dirty(self):
        self.dirty_marked = True


class _TooltipAssistEditor(EditorSubtitleAssistMixin):
    def __init__(self):
        self.settings = {
            "sub_gap_break_sec": 1.5,
            "subtitle_lora_micro_merge_gap_sec": 1.8,
            "deep_sequence_bridge_gap_sec": 0.3,
        }
        self.media_path = "/tmp/sample.mp4"
        self.timeline = SimpleNamespace(set_toolbar_tooltips=Mock())
        self._init_subtitle_assist_state()


class SubtitleAssistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_compute_subtitle_magnet_policy_separates_lora_gap_from_continuous_window(self):
        policy = compute_subtitle_magnet_policy(
            {
                "sub_gap_break_sec": 1.5,
                "subtitle_lora_micro_merge_gap_sec": 1.8,
                "deep_sequence_bridge_gap_sec": 0.3,
            }
        )

        self.assertEqual(policy["sub_gap_break_sec"], 1.5)
        self.assertEqual(policy["lora_micro_merge_gap_sec"], 1.8)
        self.assertEqual(policy["deep_bridge_gap_sec"], 0.3)
        self.assertEqual(policy["recommended_threshold_sec"], 1.8)
        self.assertEqual(policy["continuous_threshold_sec"], 3.0)

    def test_subtitle_magnet_closes_short_silence_without_merging_text_rows(self):
        merged, report = apply_netflix_subtitle_magnet(
            [
                {"line": 0, "start": 0.0, "end": 1.0, "text": "안녕", "spk": "00"},
                {"line": 1, "start": 1.6, "end": 2.4, "text": "하세요", "spk": "00"},
            ],
            threshold_sec=3.0,
            boundary_times=[],
            provisional_boundaries=[],
            vad_segments=[],
            fps=30.0,
            policy=compute_subtitle_magnet_policy(
                {
                    "sub_gap_break_sec": 1.5,
                    "subtitle_lora_micro_merge_gap_sec": 1.8,
                    "subtitle_lora_micro_merge_min_duration": 0.8,
                    "split_length_threshold": 20,
                    "deep_sequence_bridge_gap_sec": 0.3,
                }
            ),
        )

        self.assertEqual(report["closed_pairs"], 1)
        self.assertEqual(report["modes"].get("lora_micro"), 1)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["text"], "안녕")
        self.assertEqual(merged[1]["text"], "하세요")
        self.assertAlmostEqual(merged[1]["start"], 1.6, places=6)
        self.assertAlmostEqual(merged[0]["end"], merged[1]["start"], places=6)

    def test_subtitle_magnet_keeps_confirmed_cut_boundary(self):
        merged, report = apply_netflix_subtitle_magnet(
            [
                {"line": 0, "start": 0.0, "end": 1.0, "text": "앞", "spk": "00"},
                {"line": 1, "start": 1.5, "end": 2.2, "text": "뒤", "spk": "00"},
            ],
            threshold_sec=3.0,
            boundary_times=[1.25],
            provisional_boundaries=[],
            vad_segments=[],
            fps=30.0,
            policy=compute_subtitle_magnet_policy(
                {
                    "sub_gap_break_sec": 1.5,
                    "subtitle_lora_micro_merge_gap_sec": 1.8,
                    "deep_sequence_bridge_gap_sec": 0.3,
                }
            ),
        )

        self.assertEqual(report["closed_pairs"], 0)
        self.assertEqual(report["blocked"].get("confirmed_cut"), 1)
        self.assertEqual(len(merged), 2)

    def test_subtitle_magnet_does_not_close_long_gap_only_because_continuous_window_is_large(self):
        merged, report = apply_netflix_subtitle_magnet(
            [
                {"line": 0, "start": 0.0, "end": 2.0, "text": "긴 문장입니다", "spk": "00"},
                {"line": 1, "start": 4.4, "end": 5.5, "text": "다음 문장입니다", "spk": "00"},
            ],
            threshold_sec=3.0,
            boundary_times=[],
            provisional_boundaries=[],
            vad_segments=[],
            fps=30.0,
            policy=compute_subtitle_magnet_policy(
                {
                    "sub_gap_break_sec": 1.5,
                    "subtitle_lora_micro_merge_gap_sec": 1.8,
                    "deep_sequence_bridge_gap_sec": 0.3,
                    "continuous_threshold": 3.0,
                }
            ),
        )

        self.assertEqual(report["closed_pairs"], 0)
        self.assertEqual(len(merged), 2)
        self.assertGreater(merged[1]["start"] - merged[0]["end"], 2.0)

    def test_repeat_space_double_tap_advances_to_next_segment(self):
        editor = _RepeatAssistEditor()

        with patch("ui.editor.editor_subtitle_assist.time.monotonic", side_effect=[10.0, 10.2]):
            editor._handle_repeat_play_pause_shortcut("canvas_space")
            editor._handle_repeat_play_pause_shortcut("canvas_space")

        self.assertEqual(editor._active_seg_start, 1.2)
        self.assertEqual(editor.synced[-1], 1.2)
        self.assertIn(1.2, editor.seek_calls)
        self.assertTrue(editor._playing)

    def test_repeat_loop_rewinds_selected_segment_at_end(self):
        editor = _RepeatAssistEditor()
        editor._playing = True

        with patch("ui.editor.editor_subtitle_assist.time.monotonic", return_value=40.0):
            restarted = editor._maybe_loop_selected_segment(1.02)

        self.assertEqual(restarted, 0.0)
        self.assertIn(0.0, editor.seek_calls)

    def test_subtitle_magnet_marks_dirty_and_requires_manual_save(self):
        editor = _MagnetAssistEditor()

        with patch("ui.editor.editor_subtitle_assist.apply_subtitle_magnet_via_swift", return_value=None):
            changed = editor._on_subtitle_magnet_requested()

        self.assertTrue(changed)
        self.assertTrue(editor.dirty_marked)
        self.assertTrue(editor._autosave_requires_manual_save)
        self.assertIsNotNone(editor.loaded_segments)
        self.assertEqual(editor.loaded_kwargs["mark_dirty"], False)
        self.assertEqual(editor.loaded_segments[1]["start"], 1.6)
        self.assertEqual(editor._undo_mgr.push_immediate.call_count, 1)
        self.assertTrue(bool(getattr(editor, "_last_subtitle_magnet_snapshot_before", [])))
        self.assertTrue(bool(getattr(editor, "_last_subtitle_magnet_snapshot_after", [])))

    def test_subtitle_magnet_adopts_python_fallback_when_native_noops(self):
        editor = _MagnetAssistEditor()
        native_result = {
            "segments": [dict(seg) for seg in editor._segments],
            "report": {"closed_pairs": 0, "blocked": {}, "modes": {}},
        }
        fallback_segments = [
            {"line": 0, "start": 0.0, "end": 1.6, "text": "안녕", "spk": "00"},
            {"line": 1, "start": 1.6, "end": 2.4, "text": "하세요", "spk": "00"},
        ]
        fallback_report = {
            "closed_pairs": 1,
            "blocked": {},
            "modes": {"lora_micro": 1},
            "snapshot_before": [{"index": 0}],
            "snapshot_after": [{"index": 0}],
        }
        logger = SimpleNamespace(log=Mock())

        with patch("ui.editor.editor_subtitle_assist.apply_subtitle_magnet_via_swift", return_value=native_result), \
             patch("ui.editor.editor_subtitle_assist.apply_netflix_subtitle_magnet", return_value=(fallback_segments, fallback_report)) as fallback, \
             patch("ui.editor.editor_subtitle_assist.get_logger", return_value=logger):
            changed = editor._on_subtitle_magnet_requested()

        self.assertTrue(changed)
        self.assertEqual(fallback.call_count, 1)
        self.assertEqual(editor.loaded_segments[0]["end"], 1.6)
        self.assertTrue(any("python fallback adopted" in str(call.args[0]) for call in logger.log.call_args_list))

    def test_timeline_toolbar_exposes_magnet_and_repeat_controls(self):
        timeline = TimelineWidget()
        try:
            timeline.set_toolbar_tooltips(
                lock_tip="잠금 설명",
                magnet_tip="자막자석 설명",
                repeat_tip="반복재생 설명",
            )

            self.assertEqual(timeline.lock_chk.text(), "Lock Edit")
            self.assertEqual(timeline.magnet_btn.text(), "자막자석")
            self.assertEqual(timeline.repeat_chk.text(), "반복재생")
            self.assertEqual([btn.text() for btn in timeline._zoom_buttons], ["+", "-", "O", "ㅁ"])
            toolbar_layout = timeline.layout().itemAt(0).layout()
            texts = []
            for index in range(toolbar_layout.count()):
                item = toolbar_layout.itemAt(index)
                widget = item.widget()
                if widget is not None and hasattr(widget, "text"):
                    texts.append(widget.text())
                elif item.spacerItem() is not None:
                    texts.append("stretch")
            self.assertEqual(texts, ["Lock Edit", "반복재생", "stretch", "자막자석", "+", "-", "O", "ㅁ"])
            self.assertEqual(timeline.lock_chk.minimumHeight(), 24)
            self.assertEqual(timeline.lock_chk.maximumHeight(), 24)
            self.assertEqual(timeline.repeat_chk.minimumHeight(), 24)
            self.assertEqual(timeline.repeat_chk.maximumHeight(), 24)
            self.assertEqual(timeline.magnet_btn.minimumHeight(), 24)
            self.assertEqual(timeline.magnet_btn.maximumHeight(), 24)
            self.assertIn("QCheckBox", timeline.lock_chk.styleSheet())
            self.assertIn("border-radius: 7px", timeline.repeat_chk.styleSheet())
            self.assertIn("자막자석", timeline.magnet_btn.toolTip())
            self.assertIn("반복재생", timeline.repeat_chk.toolTip())
            self.assertIn("잠금", timeline.lock_chk.toolTip())
        finally:
            timeline.close()
            timeline.deleteLater()
            self.app.processEvents()

    def test_refresh_subtitle_assist_ui_skips_runtime_override_by_default(self):
        editor = _TooltipAssistEditor()

        with patch(
            "ui.editor.editor_subtitle_assist.personalization_settings_override_for_media",
            side_effect=AssertionError("runtime override should stay deferred"),
        ):
            editor._refresh_subtitle_assist_ui(allow_sync_override=False)

        editor.timeline.set_toolbar_tooltips.assert_called_once()

    def test_subtitle_magnet_policy_can_sync_runtime_override_on_demand(self):
        editor = _TooltipAssistEditor()

        with patch(
            "ui.editor.editor_subtitle_assist.personalization_settings_override_for_media",
            return_value={"subtitle_lora_micro_merge_gap_sec": 2.4},
        ) as override_loader:
            policy = editor._subtitle_magnet_policy(allow_sync_override=True)

        self.assertEqual(override_loader.call_count, 1)
        self.assertEqual(policy["lora_micro_merge_gap_sec"], 2.4)
