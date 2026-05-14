import unittest
from types import SimpleNamespace

from ui.editor.editor_canvas_state import EditorCanvasStateMixin


class _DummyTimeline:
    def __init__(self):
        self.boundary_times = None
        self.auto_gap_enabled = None

    def set_boundary_times(self, values):
        self.boundary_times = list(values)

    def set_auto_gap_segments_enabled(self, enabled):
        self.auto_gap_enabled = bool(enabled)


class _DummyEditor(EditorCanvasStateMixin):
    def __init__(self):
        self.timeline = _DummyTimeline()
        self.video_fps = 30.0
        self.reloaded = None
        self.scan_lines = None
        self.voice_activity = None
        self._live_stt_preview_segments = []
        self.schedule_count = 0

    def _reload_segments_from_list(self, segs, *, preserve_view=False, mark_dirty=True):
        self.reloaded = {
            "segments": [dict(seg) for seg in segs],
            "preserve_view": preserve_view,
            "mark_dirty": mark_dirty,
        }

    def _set_auto_cut_boundary_scan_lines(self, segments):
        self.scan_lines = list(segments)

    def set_voice_activity_segments(self, segments):
        self.voice_activity = list(segments)

    def _schedule_timeline(self):
        self.schedule_count += 1


class EditorCanvasStateTests(unittest.TestCase):
    def test_apply_loaded_canvas_state_uses_shared_loader_and_aux_state(self):
        editor = _DummyEditor()

        ordered = editor.apply_loaded_canvas_state(
            [
                {"start": 3.0, "end": 4.0, "text": "later"},
                {"start": 1.0, "end": 2.0, "text": "earlier"},
            ],
            preserve_view=True,
            mark_dirty=False,
            auto_gap_segments_enabled=False,
            boundary_times=[1.25, 2.5],
            provisional_boundaries=[{"start": 1.2, "end": 1.3}],
            voice_activity_segments=[{"start": 0.5, "end": 0.9}],
            stt_preview_segments=[{"line": 99, "text": "preview"}],
        )

        self.assertEqual([seg["text"] for seg in ordered], ["earlier", "later"])
        self.assertEqual([seg["line"] for seg in ordered], [0, 1])
        self.assertEqual([seg["text"] for seg in editor.reloaded["segments"]], ["earlier", "later"])
        self.assertTrue(editor.reloaded["preserve_view"])
        self.assertFalse(editor.reloaded["mark_dirty"])
        self.assertFalse(editor.timeline.auto_gap_enabled)
        self.assertEqual(editor.timeline.boundary_times, [1.25, 2.5])
        self.assertEqual(editor.scan_lines, [{"start": 1.2, "end": 1.3}])
        self.assertEqual(editor.voice_activity, [{"start": 0.5, "end": 0.9}])
        self.assertEqual(editor._live_stt_preview_segments, [{"line": 99, "text": "preview"}])
        self.assertEqual(editor.schedule_count, 1)

    def test_apply_loaded_canvas_state_normalizes_to_frame_grid_and_closes_micro_gap(self):
        editor = _DummyEditor()

        ordered = editor.apply_loaded_canvas_state(
            [
                {"start": 1.001, "end": 1.533, "text": "둘째"},
                {"start": 0.000, "end": 0.999, "text": "첫째"},
            ],
            preserve_view=False,
            mark_dirty=False,
        )

        self.assertEqual([seg["text"] for seg in ordered], ["첫째", "둘째"])
        self.assertAlmostEqual(ordered[0]["end"], 1.0, places=6)
        self.assertAlmostEqual(ordered[1]["start"], 1.0, places=6)
        self.assertEqual(ordered[0]["timeline_end_frame"], ordered[1]["timeline_start_frame"])
        self.assertEqual(editor.reloaded["segments"][0]["timeline_end_frame"], editor.reloaded["segments"][1]["timeline_start_frame"])

    def test_apply_canvas_aux_state_can_skip_schedule(self):
        editor = _DummyEditor()

        editor.apply_canvas_aux_state(
            boundary_times=[0.5],
            stt_preview_segments=[{"line": 1}],
            schedule_timeline=False,
        )

        self.assertEqual(editor.timeline.boundary_times, [0.5])
        self.assertEqual(editor._live_stt_preview_segments, [{"line": 1}])
        self.assertEqual(editor.schedule_count, 0)

    def test_apply_loaded_canvas_state_clamps_segments_to_video_duration(self):
        editor = _DummyEditor()
        editor.video_player = SimpleNamespace(total_time=10.0)

        ordered = editor.apply_loaded_canvas_state(
            [
                {"start": 9.8, "end": 10.6, "text": "tail"},
                {"start": 10.8, "end": 12.0, "text": "drop"},
            ],
            preserve_view=False,
            mark_dirty=False,
        )

        self.assertEqual(len(ordered), 1)
        self.assertEqual(ordered[0]["text"], "tail")
        self.assertLessEqual(float(ordered[0]["end"]), 10.0)
        self.assertEqual([seg["text"] for seg in editor.reloaded["segments"]], ["tail"])


if __name__ == "__main__":
    unittest.main()
