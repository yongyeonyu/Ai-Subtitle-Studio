# Version: 03.04.01
# Phase: PHASE2
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.timeline.timeline_canvas import TimelineCanvas
from ui.timeline.timeline_constants import DIAMOND_Y, SEG_TOP


class TimelineHitTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _canvas(self):
        canvas = TimelineCanvas()
        canvas.pps = 100.0
        canvas.total_duration = 3.0
        canvas.segments = [
            {"start": 1.0, "end": 2.0, "text": "앞", "line": 0},
            {"start": 2.0, "end": 3.0, "text": "뒤", "line": 1},
        ]
        return canvas

    def test_segment_arrow_hit_uses_exact_visible_polygon_without_margin(self):
        canvas = self._canvas()
        handle_y = SEG_TOP + 32

        hit = canvas._handle_drag_at(188, handle_y)
        self.assertIsNotNone(hit)
        self.assertEqual(hit[1], "square_right")

        self.assertIsNone(canvas._handle_drag_at(200, handle_y))

    def test_diamond_hit_has_small_margin_only(self):
        canvas = self._canvas()

        self.assertEqual(canvas._diamond_index_at(209, DIAMOND_Y, margin=5), 0)
        self.assertIsNone(canvas._diamond_index_at(211, DIAMOND_Y, margin=5))

    def test_hovered_arrow_stays_active_when_segment_objects_refresh(self):
        canvas = self._canvas()
        old_seg = canvas.segments[0]
        canvas._hover_handle = (old_seg, "right")
        canvas.segments = [
            {"start": 1.0, "end": 2.0, "text": "앞 갱신", "line": 0},
            {"start": 2.0, "end": 3.0, "text": "뒤", "line": 1},
        ]

        self.assertTrue(canvas._hover_handle_matches(canvas.segments[0], "right"))
        self.assertFalse(canvas._hover_handle_matches(canvas.segments[0], "left"))
        self.assertFalse(canvas._hover_handle_matches(canvas.segments[1], "right"))

    def test_arrow_drag_does_not_rebuild_gaps_on_every_mouse_move(self):
        canvas = self._canvas()
        canvas.segments[1]["start"] = 2.5
        seg = canvas.segments[0]
        canvas._setup_drag(seg, "square_right", canvas._x(seg["end"]))

        with patch("ui.timeline.timeline_input._build_gaps") as build_gaps:
            canvas._apply_drag(0.2)

        build_gaps.assert_not_called()
        self.assertGreater(seg["end"], 2.0)


if __name__ == "__main__":
    unittest.main()
