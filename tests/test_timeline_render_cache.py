# Version: 03.14.31
# Phase: PHASE2
import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QApplication, QScrollArea

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

    def test_viewport_paint_clip_limits_full_canvas_resize_repaint(self):
        scroll = QScrollArea()
        canvas = TimelineCanvas()
        try:
            scroll.setWidget(canvas)
            scroll.setWidgetResizable(False)
            scroll.resize(900, 340)
            canvas.setFixedWidth(120_000)
            canvas.setFixedHeight(314)
            scroll.show()
            self.app.processEvents()
            scroll.horizontalScrollBar().setValue(20_000)

            clipped = canvas._viewport_paint_clip(QRect(0, 0, 120_000, 314), pad_px=64)

            self.assertGreaterEqual(clipped.left(), 20_000 - 64)
            self.assertLessEqual(clipped.width(), scroll.viewport().width() + 128)
            self.assertLess(clipped.width(), 120_000)
        finally:
            scroll.close()
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

    def test_update_segments_does_not_precompute_full_voice_activity_lane(self):
        canvas = TimelineCanvas()
        try:
            segments = [
                {"start": float(i), "end": float(i) + 0.5, "text": f"seg {i}", "line": i}
                for i in range(500)
            ]
            canvas._refresh_voice_activity_segments = Mock(side_effect=AssertionError("full precompute should stay lazy"))

            canvas.update_segments(segments, active_sec=0.0, total_dur=600.0)

            canvas._refresh_voice_activity_segments.assert_not_called()
            self.assertEqual(canvas.voice_activity_segments, [])
        finally:
            canvas.close()

    def test_visible_voice_activity_cache_uses_only_visible_inputs(self):
        canvas = TimelineCanvas()
        try:
            visible_segments = [
                {"start": 10.0, "end": 11.0, "text": "visible", "line": 10},
                {"start": 12.0, "end": 13.0, "text": "visible 2", "line": 11},
            ]
            canvas.segments = [
                {"start": float(i), "end": float(i) + 0.5, "text": f"seg {i}", "line": i}
                for i in range(1000)
            ]
            canvas.total_duration = 2000.0
            seen = {}

            def fake_detection(segments, vad_segments, gap_segments, total_duration):
                seen["segments"] = list(segments)
                return [{"start": 10.0, "end": 13.0, "kind": "speech", "label": "음성", "color": "#34C759"}]

            with patch("ui.timeline.timeline_analysis.subtitle_detection_segments_for_editor", side_effect=fake_detection):
                markers = canvas.visible_voice_activity_segments_cached(
                    9.5,
                    13.5,
                    visible_segments,
                    [],
                    [],
                )

            self.assertEqual(seen["segments"], visible_segments)
            self.assertEqual(len(markers), 1)
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
        self.assertEqual(rows[0]["renderProfile"], "full")
        self.assertTrue(rows[0]["showText"])

    def test_scenegraph_dense_vector_profile_disables_expensive_segment_decorations(self):
        segments = [
            {"start": float(i * 0.6), "end": float(i * 0.6 + 0.45), "text": f"dense {i}", "line": i, "speaker": "00"}
            for i in range(180)
        ]

        rows = build_scenegraph_subtitle_segments(
            segments,
            pps=12.0,
            fps=24.0,
            visible_start_sec=0.0,
            visible_end_sec=24.0,
        )

        self.assertTrue(rows)
        first = rows[0]
        self.assertEqual(first["renderProfile"], "minimal")
        self.assertFalse(first["showText"])
        self.assertFalse(first["showConfidenceChips"])
        self.assertFalse(first["showSpeakerBar"])
        self.assertFalse(first["showHandles"])
        self.assertEqual(first["text"], "")
        self.assertEqual(first["confidenceChips"], [])

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
