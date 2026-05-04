# Version: 03.14.31
# Phase: PHASE2
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.timeline.timeline_canvas import TimelineCanvas


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
            self.assertEqual(canvas._paint_index_cache, {})
        finally:
            canvas.close()


if __name__ == "__main__":
    unittest.main()
