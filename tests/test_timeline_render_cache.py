# Version: 03.14.31
# Phase: PHASE2
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.timeline.timeline_scenegraph import build_scenegraph_subtitle_segments
from ui.timeline.timeline_canvas import TimelineCanvas
from ui.timeline.timeline_constants import DIAMOND_Y


class TimelineRenderCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_visible_item_index_culls_offscreen_segments(self):
        canvas = TimelineCanvas()
        try:
            segments = [
                {"start": float(i * 2), "end": float(i * 2 + 1), "text": f"seg {i}", "line": i}
                for i in range(2000)
            ]
            canvas.segments = segments
            canvas._invalidate_render_cache()

            visible = canvas._visible_items_for_paint(segments, "segments", 200.0, 208.0)

            self.assertLess(len(visible), 10)
            self.assertTrue(all(float(item["end"]) >= 200.0 and float(item["start"]) <= 208.0 for item in visible))
            self.assertEqual(canvas._paint_last_visible_counts["segments"], len(visible))
        finally:
            canvas.close()

    def test_update_segments_invalidates_render_cache(self):
        canvas = TimelineCanvas()
        try:
            first = [
                {"start": float(i * 2), "end": float(i * 2 + 1), "text": f"first {i}", "line": i}
                for i in range(80)
            ]
            second = [
                {"start": float(100 + i * 2), "end": float(100 + i * 2 + 1), "text": f"second {i}", "line": i}
                for i in range(80)
            ]

            canvas.update_segments(first, active_sec=0.0, total_dur=12.0)
            epoch_1 = canvas._render_epoch
            canvas._visible_items_for_paint(canvas.segments, "segments", 0.0, 2.0)
            self.assertIn("segments", canvas._paint_index_cache)

            canvas.update_segments(second, active_sec=10.0, total_dur=12.0)

            self.assertGreater(canvas._render_epoch, epoch_1)
            for cache in canvas._paint_index_cache.values():
                self.assertEqual(cache.get("sig", ())[-1], canvas._render_epoch)
        finally:
            canvas.close()

    def test_frame_rate_change_invalidates_render_cache(self):
        canvas = TimelineCanvas()
        try:
            canvas.segments = [
                {"start": float(i), "end": float(i + 0.5), "text": f"fps {i}", "line": i}
                for i in range(80)
            ]
            canvas._visible_items_for_paint(canvas.segments, "segments", 0.0, 3.0)
            self.assertIn("segments", canvas._paint_index_cache)
            epoch = canvas._render_epoch

            canvas.set_frame_rate(24.0)

            self.assertGreater(canvas._render_epoch, epoch)
            self.assertEqual(canvas._paint_index_cache, {})
            self.assertEqual(canvas._get_fps(), 24.0)
        finally:
            canvas.close()

    def test_scenegraph_segments_are_fps_anchored_and_visible_culled(self):
        segments = [
            {"start": 2.0, "end": 3.0, "text": "visible", "line": 0, "speaker": "00"},
            {"start": 20.0, "end": 21.0, "text": "offscreen", "line": 1, "speaker": "00"},
        ]

        rows = build_scenegraph_subtitle_segments(
            segments,
            pps=240.0,
            fps=24.0,
            visible_start_sec=1.5,
            visible_end_sec=4.0,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["text"], "visible")
        self.assertEqual(rows[0]["startFrame"], 48)
        self.assertEqual(rows[0]["endFrame"], 72)
        self.assertAlmostEqual(rows[0]["x"], 480.0)
        self.assertAlmostEqual(rows[0]["w"], 240.0)

    def test_visible_item_index_keeps_dragged_segment_when_cached_position_is_offscreen(self):
        canvas = TimelineCanvas()
        try:
            segments = [
                {"start": float(i * 2), "end": float(i * 2 + 1), "text": f"seg {i}", "line": i}
                for i in range(2000)
            ]
            canvas.segments = segments
            canvas._invalidate_render_cache()
            canvas._visible_items_for_paint(segments, "segments", 0.0, 3.0)

            dragged = segments[-1]
            canvas._drag_seg = dragged
            dragged["start"] = 12.0
            dragged["end"] = 13.0

            visible = canvas._visible_items_for_paint(segments, "segments", 11.5, 13.5)

            self.assertIn(dragged, visible)
            self.assertLess(len(visible), 12)
        finally:
            canvas._drag_seg = None
            canvas.close()

    def test_hit_candidates_are_limited_to_click_neighborhood(self):
        canvas = TimelineCanvas()
        try:
            canvas.pps = 100.0
            canvas.segments = [
                {"start": float(i * 2), "end": float(i * 2 + 1), "text": f"seg {i}", "line": i}
                for i in range(2000)
            ]
            canvas._invalidate_render_cache()

            candidates = canvas._segments_near_x_for_hit(canvas._x(500.5), pad_px=8)

            self.assertLess(len(candidates), 8)
            self.assertTrue(all(item["end"] >= 500.42 and item["start"] <= 500.58 for item in candidates))
        finally:
            canvas.close()

    def test_diamond_hit_uses_cached_sorted_pairs_for_large_timeline(self):
        canvas = TimelineCanvas()
        try:
            canvas.pps = 100.0
            canvas.segments = [
                {"start": float(i), "end": float(i + 1), "text": f"seg {i}", "line": i}
                for i in range(500)
            ]
            canvas._invalidate_render_cache()

            hit = canvas._diamond_index_at(canvas._x(250.0), DIAMOND_Y, margin=5)

            self.assertEqual(hit, 249)
            self.assertEqual(len(canvas._diamond_pairs_cache.get("pairs") or []), 499)
        finally:
            canvas.close()


if __name__ == "__main__":
    unittest.main()
