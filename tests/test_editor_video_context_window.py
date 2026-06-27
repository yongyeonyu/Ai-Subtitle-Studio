import unittest
from types import SimpleNamespace

from core.project.nle_runtime_cutover import NLE_RUNTIME_CUTOVER_SCHEMA
from ui.editor.editor_helpers import build_segment_lookup
from ui.editor.editor_segments import EditorSegmentsMixin


class _EditorHarness(EditorSegmentsMixin):
    def __init__(self, segments, playhead_sec=0.0):
        self.settings = {
            "editor_video_context_before_sec": 10.0,
            "editor_video_context_after_sec": 20.0,
            "editor_video_context_max_segments": 48,
        }
        self._active_seg_start = playhead_sec
        self.video_fps = 30.0
        self.timeline = SimpleNamespace(canvas=SimpleNamespace(playhead_sec=playhead_sec))
        self._cached_segs = list(segments)
        self._subtitle_memory_cache = build_segment_lookup(self._cached_segs)


class _Cursor:
    def __init__(self, line):
        self._line = int(line)

    def blockNumber(self):
        return self._line


class _TextEdit:
    def __init__(self, start_line, end_line, current_line):
        self._start_line = int(start_line)
        self._end_line = int(end_line)
        self._current_line = int(current_line)

    def visible_block_number_range(self, *, pad_before=42, pad_after=96):
        return self._start_line, self._end_line

    def textCursor(self):
        return _Cursor(self._current_line)


class _Highlighter:
    def __init__(self):
        self.quality_map = None
        self.visible_lines = None

    def set_quality_map(self, quality_map, visible_lines=None):
        self.quality_map = dict(quality_map)
        self.visible_lines = list(visible_lines or [])


class EditorVideoContextWindowTests(unittest.TestCase):
    def test_segment_lookup_reuses_sorted_segment_objects(self):
        segments = [
            {"start": 0.0, "end": 1.0, "text": "첫째", "line": 0},
            {"start": 1.0, "end": 2.0, "text": "둘째", "line": 1},
        ]

        lookup = build_segment_lookup(segments)

        self.assertIs(lookup["segments"][0], segments[0])
        self.assertIs(lookup["visible_segments"][1], segments[1])
        self.assertIs(lookup["line_map"][0], segments[0])

    def test_segment_lookup_sorts_only_when_needed(self):
        first = {"start": 2.0, "end": 3.0, "text": "뒤", "line": 2}
        second = {"start": 0.0, "end": 1.0, "text": "앞", "line": 0}

        lookup = build_segment_lookup([first, second])

        self.assertIs(lookup["segments"][0], second)
        self.assertIs(lookup["segments"][1], first)
        self.assertEqual(lookup["starts"], [0.0, 2.0])

    def test_video_context_uses_playhead_window_not_full_subtitle_list(self):
        segments = [
            {"start": float(i), "end": float(i) + 0.6, "text": f"seg {i}", "line": i}
            for i in range(2000)
        ]
        editor = _EditorHarness(segments, playhead_sec=500.0)

        window = editor._video_subtitle_context_for_player()

        self.assertLess(len(window), 80)
        self.assertGreater(len(window), 0)
        self.assertTrue(any(seg["start"] <= 500.0 < seg["end"] or abs(seg["start"] - 500.0) < 1.0 for seg in window))
        self.assertGreaterEqual(window[0]["start"], 489.0)
        self.assertLessEqual(window[-1]["start"], 522.0)

    def test_video_context_final_overlay_uses_nle_runtime_projection(self):
        segments = [
            {
                "id": "caption_1",
                "start": 0.0,
                "end": 1.0,
                "text": "첫째",
                "speaker": "00",
                "stt_candidates": [{"source": "STT1", "text": "raw"}],
            },
            {"id": "gap_1", "start": 1.0, "end": 2.0, "text": "", "is_gap": True},
            {"id": "preview_1", "start": 1.2, "end": 2.2, "text": "후보", "stt_pending": True},
            {"id": "caption_2", "start": 2.0, "end": 3.0, "text": "둘째", "speaker": "01"},
        ]
        editor = _EditorHarness(segments, playhead_sec=1.5)

        window = editor._video_subtitle_context_for_player()

        self.assertEqual([seg["text"] for seg in window], ["첫째", "둘째"])
        self.assertTrue(all(seg.get("_nle_runtime_surface") == "final_overlay" for seg in window))
        self.assertTrue(all(seg.get("_nle_runtime_schema") == NLE_RUNTIME_CUTOVER_SCHEMA for seg in window))
        self.assertFalse(any(seg.get("is_gap") for seg in window))
        self.assertFalse(any(seg.get("stt_pending") for seg in window))
        self.assertFalse(any("stt_candidates" in seg for seg in window))

    def test_video_context_includes_live_preview_segments_while_processing(self):
        segments = [
            {"start": 0.0, "end": 1.0, "text": "기존", "line": 0},
        ]
        editor = _EditorHarness(segments, playhead_sec=5.0)
        editor._live_editor_preview_segments = [
            {"start": 5.0, "end": 6.0, "text": "실시간 자막", "line": 1, "_live_subtitle_preview": True}
        ]

        window = editor._video_subtitle_context_for_player()

        self.assertIn("실시간 자막", [seg["text"] for seg in window])

    def test_video_context_reuses_cached_visible_window_for_same_range(self):
        segments = [
            {"start": float(i), "end": float(i) + 0.6, "text": f"seg {i}", "line": i}
            for i in range(2000)
        ]
        editor = _EditorHarness(segments, playhead_sec=500.0)

        first = editor._subtitle_memory_visible_window(center_sec=500.0)
        second = editor._subtitle_memory_visible_window(center_sec=500.0)
        third = editor._subtitle_memory_visible_window(center_sec=900.0)

        self.assertIs(first, second)
        self.assertIsNot(first, third)
        self.assertLess(len(first), 80)

    def test_context_window_caps_dense_local_segments_around_center(self):
        segments = [
            {"start": float(i) * 0.2, "end": float(i) * 0.2 + 0.12, "text": f"dense {i}", "line": i}
            for i in range(2000)
        ]
        editor = _EditorHarness([], playhead_sec=0.0)

        window = editor._subtitle_context_window_from_segments(segments, center_sec=120.0)

        self.assertLessEqual(len(window), 48)
        self.assertTrue(window[0]["start"] <= 120.0 <= window[-1]["end"])

    def test_visible_quality_map_uses_editor_viewport_not_full_document(self):
        segments = [
            {
                "start": float(i),
                "end": float(i) + 0.5,
                "text": f"seg {i}",
                "line": i,
                "quality": {"confidence_label": "red" if i == 1000 else "green"},
            }
            for i in range(2000)
        ]
        editor = _EditorHarness(segments, playhead_sec=1000.0)
        editor.text_edit = _TextEdit(990, 1010, 1000)
        editor._highlighter = _Highlighter()

        editor._refresh_visible_quality_map()

        self.assertLess(len(editor._highlighter.quality_map), 32)
        self.assertIn(1000, editor._highlighter.quality_map)
        self.assertNotIn(10, editor._highlighter.quality_map)
        self.assertEqual(editor._highlighter.visible_lines[0], 990)
        self.assertEqual(editor._highlighter.visible_lines[-1], 1010)


if __name__ == "__main__":
    unittest.main()
