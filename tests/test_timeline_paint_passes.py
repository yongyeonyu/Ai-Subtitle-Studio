import unittest

from PyQt6.QtCore import QRect

from ui.timeline.paint_passes import (
    build_aggregate_vector_subtitle_paint_plan,
    build_gap_lane_paint_plan,
    build_stt_preview_lane_paint_plan,
    coalesce_rects_by_row,
    visible_pixel_span,
)


def _rect_tuple(rect):
    return (rect.x(), rect.y(), rect.width(), rect.height())


class TimelinePaintPassesTests(unittest.TestCase):
    def test_coalesce_rects_by_row_merges_only_same_lane_neighbors(self):
        merged = coalesce_rects_by_row(
            [
                QRect(10, 20, 5, 8),
                QRect(16, 20, 4, 8),
                QRect(40, 20, 5, 8),
                QRect(12, 40, 5, 8),
            ],
            max_gap_px=1,
        )

        self.assertEqual([_rect_tuple(rect) for rect in merged], [(10, 20, 10, 8), (40, 20, 5, 8), (12, 40, 5, 8)])

    def test_gap_lane_plan_keeps_only_active_items_in_compact_mode(self):
        plan = build_gap_lane_paint_plan(
            gaps=[
                {"start": 1.0, "end": 1.4, "active": False},
                {"start": 2.0, "end": 2.6, "active": True},
            ],
            clip_left=0,
            clip_right=200,
            seg_top=10,
            seg_bot=30,
            overview_mode=True,
            ultra_dense_segment_mode=False,
            dense_segment_mode=False,
            show_gap_insert_controls=True,
            sec_to_x=lambda sec: int(sec * 20),
            icon_rect_builder=lambda x1, x2: QRect(x1, 10, 12, 12),
            plus_rect_builder=lambda x1, x2: QRect(x2 - 12, 10, 12, 12),
        )

        self.assertTrue(plan.compact_gap_mode)
        self.assertFalse(plan.inactive_rects)
        self.assertEqual(len(plan.active_items), 1)
        self.assertEqual(_rect_tuple(plan.active_items[0].rect), (40, 10, 12, 20))

    def test_preview_plan_merges_ultra_dense_segments_without_detail_items(self):
        preview_segments = [
            {"start": idx * 0.05, "end": (idx * 0.05) + 0.03, "text": f"p{idx}"}
            for idx in range(100)
        ]

        plan = build_stt_preview_lane_paint_plan(
            preview_segments=preview_segments,
            clip_left=0,
            clip_right=200,
            lane_top=40,
            lane_bot=70,
            pps=8.0,
            ultra_dense_segment_mode=True,
            selected_final_stt_segments=[],
            selected_final_stt_index={},
            sec_to_x=lambda sec: int(sec * 20),
        )

        self.assertTrue(plan.aggregate_rects)
        self.assertFalse(plan.items)

    def test_preview_plan_keeps_detail_selection_state(self):
        seg = {"start": 1.0, "end": 1.8, "text": "preview"}
        plan = build_stt_preview_lane_paint_plan(
            preview_segments=[seg],
            clip_left=0,
            clip_right=200,
            lane_top=40,
            lane_bot=70,
            pps=20.0,
            ultra_dense_segment_mode=False,
            selected_final_stt_segments=[],
            selected_final_stt_index={},
            sec_to_x=lambda sec: int(sec * 20),
            selection_state_map={id(seg): "manual"},
        )

        self.assertFalse(plan.aggregate_rects)
        self.assertEqual(len(plan.items), 1)
        self.assertEqual(plan.items[0].selection_state, "manual")
        self.assertTrue(plan.items[0].is_selected)

    def test_preview_plan_uses_stt_word_span_instead_of_window_lead_in(self):
        seg = {
            "start": 62.0,
            "end": 66.0,
            "timeline_start": 62.0,
            "timeline_end": 66.0,
            "text": "아 이게 시림프 갈릭 소스",
            "stt_pending": True,
            "stt_preview_source": "STT1",
            "words": [
                {"word": "아", "start": 67.1, "end": 67.25},
                {"word": "소스", "start": 68.2, "end": 68.9},
            ],
        }

        plan = build_stt_preview_lane_paint_plan(
            preview_segments=[seg],
            clip_left=0,
            clip_right=1000,
            lane_top=40,
            lane_bot=70,
            pps=20.0,
            ultra_dense_segment_mode=False,
            selected_final_stt_segments=[],
            selected_final_stt_index={},
            sec_to_x=lambda sec: int(sec * 10),
        )

        self.assertEqual(len(plan.items), 1)
        self.assertEqual(plan.items[0].rect.x(), int(67.1 * 10) + 1)

    def test_visible_pixel_span_drops_tiny_clipped_edge_fragment(self):
        self.assertIsNone(
            visible_pixel_span(100, 108, clip_left=0, clip_right=100, min_edge_fragment_px=2)
        )
        self.assertEqual(
            visible_pixel_span(98, 108, clip_left=0, clip_right=100, min_edge_fragment_px=2),
            (98, 101),
        )

    def test_preview_plan_drops_right_edge_fragment(self):
        seg = {"start": 10.0, "end": 10.8, "text": "edge"}
        plan = build_stt_preview_lane_paint_plan(
            preview_segments=[seg],
            clip_left=0,
            clip_right=100,
            lane_top=40,
            lane_bot=70,
            pps=20.0,
            ultra_dense_segment_mode=False,
            selected_final_stt_segments=[],
            selected_final_stt_index={},
            sec_to_x=lambda sec: int(sec * 10),
        )

        self.assertFalse(plan.aggregate_rects)
        self.assertFalse(plan.items)

    def test_aggregate_vector_plan_keeps_active_segment_for_detail(self):
        segments = [
            {"line": 0, "start": 0.0, "end": 0.4},
            {"line": 1, "start": 0.5, "end": 0.9},
            {"line": 2, "start": 1.0, "end": 1.4},
        ] * 40

        plan = build_aggregate_vector_subtitle_paint_plan(
            segments=segments,
            clip_left=0,
            clip_right=400,
            pps=8.0,
            subtitle_top=100,
            subtitle_bot=130,
            speaker_top=140,
            speaker_bot=160,
            ultra_dense_segment_mode=True,
            active_seg_start=0.5,
            hover_line=None,
        )

        self.assertTrue(plan.enabled)
        self.assertTrue(plan.subtitle_rects)
        self.assertTrue(any(abs(seg["start"] - 0.5) < 1e-6 for seg in plan.detail_segments))

    def test_aggregate_vector_plan_drops_right_edge_fragment(self):
        segments = [
            {"line": idx, "start": idx * 0.1, "end": (idx * 0.1) + 0.08}
            for idx in range(95)
        ]
        segments.append({"line": 999, "start": 10.0, "end": 10.8})

        plan = build_aggregate_vector_subtitle_paint_plan(
            segments=segments,
            clip_left=0,
            clip_right=100,
            pps=10.0,
            subtitle_top=100,
            subtitle_bot=130,
            speaker_top=140,
            speaker_bot=160,
            ultra_dense_segment_mode=True,
            active_seg_start=None,
            hover_line=None,
        )

        self.assertTrue(plan.enabled)
        self.assertTrue(plan.subtitle_rects)
        self.assertTrue(all(rect.x() + rect.width() <= 101 for rect in plan.subtitle_rects))


if __name__ == "__main__":
    unittest.main()
