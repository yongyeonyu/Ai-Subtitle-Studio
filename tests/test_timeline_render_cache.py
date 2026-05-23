# Version: 03.14.31
# Phase: PHASE2
import os
import unittest
from unittest.mock import Mock, patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QColor, QImage, QPainter, QPalette, QRegion
from PyQt6.QtWidgets import QApplication, QScrollArea

from ui.timeline.timeline_scenegraph import build_scenegraph_subtitle_segments
from ui.timeline.timeline_canvas import TimelineCanvas
from ui.timeline.timeline_constants import CANVAS_H, DIAMOND_Y, RULER_H, SCORE_H, SCORE_TOP, SEG_TOP, STT1_BOT, STT1_TOP, STT2_TOP, STT_PREVIEW_VERTICAL_INSET, SUBTITLE_BOT, SUBTITLE_TOP, WAVE_H
from ui.timeline.timeline_segment_style import speaker_segment_fill_hex
from ui.timeline.stt_preview_layout import stt_preview_lane_geometry
from ui.timeline.paint_passes import build_cut_boundary_work_lane_paint_plan
from ui.timeline.timeline_roughcut_paint import expanded_roughcut_marker_span
from ui.timeline.timeline_widget import TimelineWidget


class _NoEqualitySegment(dict):
    def __eq__(self, other):
        raise AssertionError("adjacent segment lookup should use identity cache, not list.index equality scans")


class _NoBoolRows:
    def __init__(self, rows):
        self._rows = list(rows)

    def __bool__(self):
        raise AssertionError("timeline paint rows should not be truth-tested")

    def __iter__(self):
        return iter(self._rows)


class _FakeScenegraphLayer:
    def __init__(self):
        self.last_kwargs = None
        self.last_rect = None
        self.visible = False
        self.raise_calls = 0

    def set_geometry(self, rect):
        self.last_rect = rect

    def set_visible(self, visible: bool):
        self.visible = bool(visible)

    def set_state(self, **kwargs):
        self.last_kwargs = dict(kwargs)
        return len(kwargs.get("segments") or [])

    def raise_(self):
        self.raise_calls += 1


class _UpdateRecordingTimelineCanvas(TimelineCanvas):
    def __init__(self):
        self.update_calls = []
        super().__init__()

    def update(self, *args):  # type: ignore[override]
        self.update_calls.append(args)


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

    def test_viewport_region_fallback_logs_once_and_repaints_full_canvas(self):
        canvas = _UpdateRecordingTimelineCanvas()
        try:
            canvas._viewport_paint_clip = Mock(side_effect=ValueError("bad clip"))
            canvas._log_timeline_nonfatal_once = Mock()

            canvas._update_viewport_region()

            canvas._log_timeline_nonfatal_once.assert_called_once()
            self.assertIn((), canvas.update_calls)
        finally:
            canvas.close()

    def test_voice_activity_refresh_failure_logs_once_and_recovers_empty_lane(self):
        canvas = TimelineCanvas()
        try:
            canvas.segments = [{"start": 0.0, "end": 1.0, "text": "a"}]
            canvas._log_timeline_nonfatal_once = Mock()

            with patch("ui.timeline.timeline_analysis.voice_activity_segments_for_editor", side_effect=RuntimeError("bad vad")):
                canvas._refresh_voice_activity_segments()

            canvas._log_timeline_nonfatal_once.assert_called_once()
            self.assertEqual(canvas.voice_activity_segments, [])
            self.assertFalse(canvas._voice_activity_segments_external)
        finally:
            canvas.close()

    def test_segment_store_reuses_identical_visible_window(self):
        canvas = TimelineCanvas()
        try:
            segments = [
                {"start": float(i * 2), "end": float(i * 2 + 1), "text": f"seg {i}", "line": i}
                for i in range(2000)
            ]
            canvas.segments = segments
            canvas._invalidate_render_cache()

            first = canvas._visible_items_for_paint(segments, "segments", 200.0, 208.0)
            second = canvas._visible_items_for_paint(segments, "segments", 200.0, 208.0)

            self.assertIs(first, second)
            self.assertTrue(first)
            self.assertIs(canvas._segment_store.rows, canvas.segments)
        finally:
            canvas.close()

    def test_visible_segment_lane_cache_reuses_cached_lane_partition(self):
        canvas = TimelineCanvas()
        try:
            canvas.segments = [
                {"start": 1.0, "end": 2.0, "text": "final", "line": 0},
                {
                    "start": 2.0,
                    "end": 3.0,
                    "text": "stt1",
                    "line": 1,
                    "stt_pending": True,
                    "_live_stt_preview": True,
                    "stt_preview_source": "STT1",
                },
                {
                    "start": 2.0,
                    "end": 3.0,
                    "text": "stt2",
                    "line": 2,
                    "stt_pending": True,
                    "_live_stt_preview": True,
                    "stt_preview_source": "STT2",
                },
                {
                    "start": 2.0,
                    "end": 3.0,
                    "text": "stt1",
                    "line": 3,
                    "stt_selected_source": "STT1",
                    "stt_candidates": [{"source": "STT1", "text": "stt1"}, {"source": "STT2", "text": "stt2"}],
                },
            ]
            visible = canvas.visible_segments_for_time_window(0.0, 6.0, pad_sec=0.0)

            first = canvas.visible_segment_lanes_cached(visible)
            second = canvas.visible_segment_lanes_cached(list(visible))

            self.assertIs(first, second)
            self.assertEqual([seg["text"] for seg in first["final_segments"]], ["final", "stt1"])
            self.assertEqual([seg["text"] for seg in first["selected_final_segments"]], ["stt1"])
            self.assertEqual([seg["text"] for seg in first["stt1_preview_segments"]], ["stt1"])
            self.assertEqual([seg["text"] for seg in first["stt2_preview_segments"]], ["stt2"])
            self.assertEqual([seg["text"] for seg in first["stt1_checked_segments"]], ["stt1"])
            self.assertEqual([seg["text"] for seg in first["stt2_checked_segments"]], ["stt1"])
            self.assertEqual(len(first["selected_final_index"].get("rows") or []), 1)
            self.assertEqual(first["stt1_lane_count"], 1)
            self.assertEqual(first["stt2_lane_count"], 1)
            self.assertEqual(first["stt_selection_states"].get(id(first["stt1_preview_segments"][0])), "manual")
            self.assertEqual(first["stt_selection_states"].get(id(first["stt2_preview_segments"][0])), "unselected")
        finally:
            canvas.close()

    def test_visible_segment_lane_cache_refreshes_when_stt_checked_metadata_changes(self):
        canvas = TimelineCanvas()
        try:
            canvas.segments = [
                {"start": 1.0, "end": 2.0, "text": "final", "line": 0},
            ]
            visible = canvas.visible_segments_for_time_window(0.0, 3.0, pad_sec=0.0)

            first = canvas.visible_segment_lanes_cached(visible)
            canvas.segments[0]["stt_candidates"] = [{"source": "STT2", "text": "보강 후보"}]
            second = canvas.visible_segment_lanes_cached(visible)

            self.assertIsNot(first, second)
            self.assertEqual(second["stt2_checked_segments"], [canvas.segments[0]])
        finally:
            canvas.close()

    def test_stt_candidate_hit_test_respects_overlapping_preview_sublanes(self):
        canvas = TimelineCanvas()
        try:
            first = {
                "start": 1.0,
                "end": 2.0,
                "text": "아까 뭐래?",
                "line": 1,
                "stt_pending": True,
                "_live_stt_preview": True,
                "stt_preview_source": "STT1",
            }
            second = {
                "start": 1.1,
                "end": 2.1,
                "text": "아까 뭐래? 커피준데? 어",
                "line": 2,
                "stt_pending": True,
                "_live_stt_preview": True,
                "stt_preview_source": "STT1",
            }
            canvas.resize(900, CANVAS_H)
            canvas.pps = 300.0
            canvas.segments = [first, second]
            canvas._invalidate_render_cache()

            x = canvas._x(1.5)
            first_top, first_h = stt_preview_lane_geometry(STT1_TOP, STT1_BOT, 0, 2, inset=STT_PREVIEW_VERTICAL_INSET)
            second_top, second_h = stt_preview_lane_geometry(STT1_TOP, STT1_BOT, 1, 2, inset=STT_PREVIEW_VERTICAL_INSET)

            self.assertIs(canvas._stt_candidate_at(x, first_top + first_h // 2), first)
            self.assertIs(canvas._stt_candidate_at(x, second_top + second_h // 2), second)
        finally:
            canvas.close()

    def test_stt_candidate_hit_test_uses_word_span_for_lead_in_window(self):
        canvas = TimelineCanvas()
        try:
            seg = {
                "start": 62.0,
                "end": 66.0,
                "text": "아 이게 시림프 갈릭 소스",
                "line": 1,
                "stt_pending": True,
                "_live_stt_preview": True,
                "stt_preview_source": "STT1",
                "words": [
                    {"word": "아", "start": 67.1, "end": 67.25},
                    {"word": "소스", "start": 68.2, "end": 68.9},
                ],
            }
            canvas.resize(900, CANVAS_H)
            canvas.pps = 100.0
            canvas.segments = [seg]
            canvas._invalidate_render_cache()

            top, height = stt_preview_lane_geometry(
                STT1_TOP,
                STT1_BOT,
                0,
                1,
                inset=STT_PREVIEW_VERTICAL_INSET,
            )

            self.assertIs(canvas._stt_candidate_at(canvas._x(67.5), top + height // 2), seg)
            self.assertIsNone(canvas._stt_candidate_at(canvas._x(63.0), top + height // 2))
        finally:
            canvas.close()

    def test_cut_boundary_work_lane_plan_filters_visible_rows(self):
        plan = build_cut_boundary_work_lane_paint_plan(
            official_rows=[
                {"timeline_sec": 1.0, "source": "visual", "status": "verified"},
                {"timeline_sec": 9.9, "source": "visual", "status": "verified"},
            ],
            scan_rows=[
                {"time": 1.0, "status": "verified", "source": "visual"},
                {"time": 2.0, "status": "pending", "source": "visual", "line_style": "dot", "ui_label": "대기"},
            ],
            visible_start_sec=0.0,
            visible_end_sec=3.0,
            clip_left=0,
            clip_right=400,
            total_duration=10.0,
            fps=100.0,
            dense_segment_mode=False,
            sec_to_x=lambda sec: int(round(sec * 100.0)),
            visible_filter=lambda rows, _key, start, end, pad_sec=0.0: [
                row
                for row in rows
                if start - pad_sec <= float((row if not isinstance(row, dict) else row.get("timeline_sec", row.get("time", 0.0))) or 0.0) <= end + pad_sec
            ],
        )

        self.assertTrue(plan.has_items)
        self.assertEqual([item.kind for item in plan.lines], ["official", "scan", "scan"])
        self.assertEqual(plan.lines[0].x, 100)
        self.assertEqual(plan.lines[1].x, 99)
        self.assertEqual(list(plan.labels), [])

    def test_cut_boundary_work_lane_plan_accepts_streaming_rows_without_truth_testing(self):
        plan = build_cut_boundary_work_lane_paint_plan(
            official_rows=_NoBoolRows([{"timeline_sec": 1.0, "source": "visual", "status": "verified"}]),
            scan_rows=_NoBoolRows([{"time": 2.0, "status": "pending", "source": "visual"}]),
            visible_start_sec=0.0,
            visible_end_sec=3.0,
            clip_left=0,
            clip_right=400,
            total_duration=10.0,
            fps=100.0,
            dense_segment_mode=False,
            sec_to_x=lambda sec: int(round(sec * 100.0)),
        )

        self.assertEqual([item.kind for item in plan.lines], ["official", "scan"])

    def test_project_loaded_overlapping_stt_preview_candidates_split_to_two_sublanes(self):
        canvas = TimelineCanvas()
        try:
            canvas.segments = [
                {"start": 0.0, "end": 2.0, "text": "final", "line": 0},
                {
                    "start": 0.0,
                    "end": 2.0,
                    "text": "STT1 A",
                    "line": 10,
                    "stt_pending": True,
                    "_live_stt_preview": True,
                    "stt_preview_source": "STT1",
                },
                {
                    "start": 0.5,
                    "end": 2.2,
                    "text": "STT1 B",
                    "line": 11,
                    "stt_pending": True,
                    "_live_stt_preview": True,
                    "stt_preview_source": "STT1",
                },
                {
                    "start": 2.3,
                    "end": 3.0,
                    "text": "STT1 C",
                    "line": 12,
                    "stt_pending": True,
                    "_live_stt_preview": True,
                    "stt_preview_source": "STT1",
                },
                {
                    "start": 0.0,
                    "end": 2.0,
                    "text": "STT2 A",
                    "line": 20,
                    "stt_pending": True,
                    "_live_stt_preview": True,
                    "stt_preview_source": "STT2",
                },
                {
                    "start": 0.4,
                    "end": 1.6,
                    "text": "STT2 B",
                    "line": 21,
                    "stt_pending": True,
                    "_live_stt_preview": True,
                    "stt_preview_source": "STT2",
                },
            ]
            visible = canvas.visible_segments_for_time_window(0.0, 4.0, pad_sec=0.0)

            lane_data = canvas.visible_segment_lanes_cached(visible)

            self.assertEqual(lane_data["stt1_lane_count"], 2)
            self.assertEqual(lane_data["stt2_lane_count"], 2)
            stt1_lanes = {
                lane_data["stt1_lane_map"][id(seg)]
                for seg in lane_data["stt1_preview_segments"][:2]
            }
            stt2_lanes = {
                lane_data["stt2_lane_map"][id(seg)]
                for seg in lane_data["stt2_preview_segments"][:2]
            }
            self.assertEqual(stt1_lanes, {0, 1})
            self.assertEqual(stt2_lanes, {0, 1})
            self.assertIn(lane_data["stt1_lane_map"][id(lane_data["stt1_preview_segments"][2])], {0, 1})
        finally:
            canvas.close()

    def test_visible_stt_preview_sublane_does_not_flip_when_overlap_neighbor_scrolls_out(self):
        canvas = TimelineCanvas()
        try:
            first = {
                "start": 1.0,
                "end": 2.0,
                "text": "STT1 A",
                "line": 10,
                "stt_pending": True,
                "_live_stt_preview": True,
                "stt_preview_source": "STT1",
            }
            second = {
                "start": 1.1,
                "end": 3.0,
                "text": "STT1 B",
                "line": 11,
                "stt_pending": True,
                "_live_stt_preview": True,
                "stt_preview_source": "STT1",
            }
            canvas.segments = [first, second]
            canvas._invalidate_render_cache()

            full = canvas.visible_segment_lanes_cached([first, second])
            bottom_lane = full["stt1_lane_map"][id(second)]
            bottom_count = full["stt1_lane_count"]
            canvas._invalidate_render_cache()
            only_second = canvas.visible_segment_lanes_cached([second])

            self.assertEqual(bottom_count, 2)
            self.assertEqual(bottom_lane, 1)
            self.assertEqual(only_second["stt1_lane_count"], 2)
            self.assertEqual(only_second["stt1_lane_map"][id(second)], 1)
        finally:
            canvas.close()

    def test_active_segment_repaint_rect_during_playback_stays_in_subtitle_band(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(1600, canvas.height())
            canvas.segments = [
                {"start": 1.0, "end": 2.0, "text": "final", "line": 0},
                {"start": 2.0, "end": 3.0, "text": "next", "line": 1},
            ]
            canvas._timeline_playback_active = lambda: True

            canvas.set_active(1.0)
            rect = canvas._active_segment_repaint_rect(playback_focus=True)

            self.assertEqual(rect.top(), max(0, SUBTITLE_TOP - 2))
            self.assertLessEqual(rect.bottom(), SUBTITLE_BOT + 3)
        finally:
            canvas.close()

    def test_clear_active_visual_repaints_full_canvas_and_resets_active_keys(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(1600, canvas.height())
            canvas.segments = [
                {"start": 1.0, "end": 2.0, "text": "final", "line": 0},
                {"start": 2.0, "end": 3.0, "text": "next", "line": 1},
            ]
            canvas.set_active(1.0)

            with patch.object(canvas, "update") as update:
                canvas.clear_active_visual()

            self.assertIsNone(canvas.active_seg_start)
            self.assertIsNone(canvas.active_seg_line)
            update.assert_called_once_with()
        finally:
            canvas.close()

    def test_playback_state_does_not_change_timeline_body_pixels_with_overlay_playhead(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(1200, CANVAS_H)
            canvas.setFixedWidth(1200)
            canvas.total_duration = 8.0
            canvas.pps = 140.0
            canvas._external_playhead_overlay = True
            canvas.playhead_sec = 2.0
            canvas.segments = [
                {"start": 0.8, "end": 2.6, "text": "마카오 영상 테스트", "line": 0},
                {"start": 2.8, "end": 4.4, "text": "잔상 확인 구간", "line": 1},
                {"start": 0.8, "end": 2.6, "text": "마카오 영상 테스트", "line": 10, "stt_pending": True},
            ]
            canvas._invalidate_render_cache()

            def _render_body(playback_active: bool) -> bytes:
                canvas._timeline_playback_active = lambda: bool(playback_active)
                image = QImage(canvas.size(), QImage.Format.Format_ARGB32_Premultiplied)
                image.fill(0)
                canvas.render(image)
                data = bytes(image.bits().asstring(image.sizeInBytes()))
                stride = image.bytesPerLine()
                score_top = int(SCORE_TOP)
                score_bottom = int(SCORE_TOP + SCORE_H + 1)
                return data[: score_top * stride] + data[score_bottom * stride :]

            self.assertEqual(_render_body(False), _render_body(True))
        finally:
            canvas.close()

    def test_active_subtitle_segment_never_renders_as_white_fill(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(1200, CANVAS_H)
            canvas.setFixedWidth(1200)
            canvas.total_duration = 8.0
            canvas.pps = 140.0
            canvas.playhead_sec = 0.0
            canvas._timeline_playback_active = lambda: True
            canvas.segments = [
                {"start": 0.8, "end": 2.6, "text": "재생 선택 구간", "line": 0},
                {"start": 2.8, "end": 4.4, "text": "다음 자막", "line": 1},
            ]
            canvas.set_active(0.8)
            canvas._invalidate_render_cache()

            image = QImage(canvas.size(), QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(0)
            canvas.render(image)

            sample = image.pixelColor(int(canvas._x(1.8)), (SUBTITLE_TOP + SUBTITLE_BOT) // 2)
            self.assertFalse(sample.red() > 245 and sample.green() > 245 and sample.blue() > 245)
        finally:
            canvas.close()

    def test_inline_editor_viewport_uses_segment_dark_palette_when_selected(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(1200, CANVAS_H)
            canvas.setFixedWidth(1200)
            canvas.total_duration = 8.0
            canvas.pps = 140.0
            canvas.segments = [
                {"start": 0.8, "end": 2.6, "text": "선택 자막", "line": 0},
            ]
            canvas.show()
            self.app.processEvents()

            canvas.start_inline_edit(0, 0.8)
            self.app.processEvents()

            editor = getattr(canvas, "_inline_editor", None)
            self.assertIsNotNone(editor)
            self.assertTrue(editor.isVisible())
            for target in (editor, editor.viewport()):
                base = target.palette().color(QPalette.ColorRole.Base)
                window = target.palette().color(QPalette.ColorRole.Window)
                self.assertNotEqual(base.name(), QColor("#FFFFFF").name())
                self.assertNotEqual(window.name(), QColor("#FFFFFF").name())
        finally:
            canvas.close()

    def test_roughcut_lane_playback_render_stays_stable_with_dense_markers(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(1200, CANVAS_H)
            canvas.setFixedWidth(1200)
            canvas.total_duration = 8.0
            canvas.pps = 140.0
            canvas._external_playhead_overlay = True
            canvas.playhead_sec = 2.0
            canvas.segments = [
                {"start": 0.8, "end": 2.6, "text": "마카오 영상 테스트", "line": 0},
            ]
            dense_markers = [
                {
                    "kind": "roughcut_major",
                    "label": "A",
                    "display_label": "A",
                    "title": "A",
                    "status": "confirmed",
                    "color": "#34C759",
                    "start": i * 0.08,
                    "end": i * 0.08 + 0.08,
                }
                for i in range(60)
            ]
            canvas.roughcut_major_markers_cached = lambda: list(dense_markers)
            canvas._invalidate_render_cache()

            def _render_body(playback_active: bool) -> bytes:
                canvas._timeline_playback_active = lambda: bool(playback_active)
                image = QImage(canvas.size(), QImage.Format.Format_ARGB32_Premultiplied)
                image.fill(0)
                canvas.render(image)
                data = bytes(image.bits().asstring(image.sizeInBytes()))
                stride = image.bytesPerLine()
                score_top = int(SCORE_TOP)
                score_bottom = int(SCORE_TOP + SCORE_H + 1)
                return data[: score_top * stride] + data[score_bottom * stride :]

            self.assertEqual(_render_body(False), _render_body(True))
        finally:
            canvas.close()

    def test_roughcut_lane_partial_strip_repaint_keeps_long_marker_continuous(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(1200, CANVAS_H)
            canvas.setFixedWidth(1200)
            canvas.total_duration = 8.0
            canvas.pps = 140.0
            canvas._external_playhead_overlay = True
            canvas.playhead_sec = 2.0
            canvas.segments = [
                {"start": 0.8, "end": 2.6, "text": "마카오 영상 테스트", "line": 0},
            ]
            canvas.roughcut_major_markers_cached = lambda: [
                {
                    "kind": "roughcut_major",
                    "label": "A",
                    "display_label": "A - test",
                    "title": "A",
                    "status": "confirmed",
                    "color": "#34C759",
                    "start": 1.0,
                    "end": 5.0,
                }
            ]
            canvas._invalidate_render_cache()
            canvas.show()
            self.app.processEvents()

            strip = QImage(canvas.size(), QImage.Format.Format_ARGB32_Premultiplied)
            strip.fill(0)
            painter = QPainter(strip)
            for x in range(0, canvas.width(), 24):
                src = QRect(x, 0, min(24, canvas.width() - x), canvas.height())
                canvas.render(painter, QPoint(x, 0), QRegion(src))
            painter.end()

            lane_top = RULER_H + WAVE_H + 5
            lane_h = max(18, SEG_TOP - lane_top - 7)
            box_top = lane_top + 3
            box_h = max(12, lane_h - 6)
            sample_y = box_top + (box_h // 2)
            background_pixel = strip.pixel(int(canvas._x(7.6)), sample_y)

            marker_x1, marker_x2 = expanded_roughcut_marker_span(canvas._x(1.0), canvas._x(5.0))
            marker_start_x = int(marker_x1) + 8
            marker_end_x = int(marker_x2) - 8
            self.assertGreater(marker_end_x, marker_start_x)
            interior_background_hits = sum(
                1
                for x in range(marker_start_x, marker_end_x)
                if strip.pixel(x, sample_y) == background_pixel
            )
            self.assertEqual(interior_background_hits, 0)
        finally:
            canvas.close()

    def test_roughcut_marker_visuals_are_50_percent_larger(self):
        lane_top = RULER_H + WAVE_H + 5
        lane_h = max(18, SEG_TOP - lane_top - 7)

        self.assertEqual(lane_h, 33)
        self.assertEqual(expanded_roughcut_marker_span(100, 140), (90, 150))

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

    def test_canvas_height_bonus_keeps_viewport_timeline_pixels_visible(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(1400, 720)
            timeline.show()
            self.app.processEvents()

            timeline.update_segments(
                [
                    {"start": 0.4, "end": 2.8, "text": "roughcut", "line": 0},
                    {"start": 3.0, "end": 5.2, "text": "final", "line": 1},
                    {
                        "start": 3.0,
                        "end": 5.2,
                        "text": "stt1",
                        "line": 10,
                        "stt_pending": True,
                        "_live_stt_preview": True,
                        "stt_preview_source": "STT1",
                    },
                    {
                        "start": 3.0,
                        "end": 5.2,
                        "text": "stt2",
                        "line": 11,
                        "stt_pending": True,
                        "_live_stt_preview": True,
                        "stt_preview_source": "STT2",
                    },
                ],
                active_sec=0.0,
                total_dur=8.0,
            )
            waveform = np.zeros(800, dtype=np.float32)
            waveform[40:180] = 0.5
            waveform[300:520] = 0.8
            waveform[600:720] = 0.4
            timeline.canvas.set_waveform(waveform)
            self.app.processEvents()

            def _render_viewport_image():
                viewport = timeline.scroll.viewport()
                image = QImage(viewport.size(), QImage.Format.Format_ARGB32_Premultiplied)
                image.fill(0)
                viewport.render(image)
                return image

            before = _render_viewport_image()
            timeline.set_canvas_height_bonus(140)
            self.app.processEvents()
            after = _render_viewport_image()
            overlap = after.copy(0, 0, before.width(), before.height())

            before_bits = before.bits()
            before_bits.setsize(before.sizeInBytes())
            overlap_bits = overlap.bits()
            overlap_bits.setsize(overlap.sizeInBytes())

            self.assertEqual(bytes(before_bits), bytes(overlap_bits))
            self.assertTrue(timeline._playhead_overlay.isHidden())
            self.assertFalse(getattr(timeline.canvas, "_external_playhead_overlay", True))
        finally:
            timeline.close()

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
            self.assertIsNotNone(canvas._segment_store)

            canvas.update_segments(second, active_sec=10.0, total_dur=12.0)

            self.assertGreater(canvas._render_epoch, epoch_1)
            self.assertIsNotNone(canvas._segment_store)
            self.assertEqual(len(canvas._segment_store.rows), len(second))
        finally:
            canvas.close()

    def test_scan_boundary_updates_skip_identical_repaints(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.canvas.setFixedWidth(120_000)
            timeline.show()
            self.app.processEvents()
            timeline.canvas.update = Mock()

            first = [{"timeline_sec": 12.0, "status": "pending", "detector_stage": "pioneer"}]
            same = [{"timeline_sec": 12.0, "status": "pending", "detector_stage": "pioneer"}]
            verifying = [{"timeline_sec": 12.0, "status": "verifying", "detector_stage": "follower"}]

            self.assertTrue(timeline.set_scan_boundary_times(first))
            self.assertEqual(timeline.canvas.update.call_count, 1)
            dirty = timeline.canvas.update.call_args.args[0]
            self.assertIsInstance(dirty, QRect)
            self.assertLess(dirty.height(), timeline.canvas.height())

            timeline.canvas.update.reset_mock()
            self.assertFalse(timeline.set_scan_boundary_times(same))
            timeline.canvas.update.assert_not_called()

            self.assertTrue(timeline.set_scan_boundary_times(verifying))
            self.assertEqual(timeline.canvas.update.call_count, 1)
        finally:
            timeline.close()

    def test_boundary_updates_invalidate_snap_cache_without_repaint(self):
        timeline = TimelineWidget()
        try:
            timeline.canvas.update = Mock()
            timeline.canvas._drag_snap_base_cache_key = object()
            timeline.canvas._drag_snap_base_candidates = [{"sec": 1.0}]

            self.assertTrue(timeline.set_boundary_times([1.0, 2.0]))
            self.assertIsNone(timeline.canvas._drag_snap_base_cache_key)
            self.assertEqual(timeline.canvas._drag_snap_base_candidates, [])
            timeline.canvas.update.assert_not_called()

            self.assertFalse(timeline.set_boundary_times([1.0, 2.0]))
            timeline.canvas.update.assert_not_called()

            timeline.canvas.boundary_times = [9.0]
            self.assertTrue(timeline.set_boundary_times([]))
            self.assertEqual(timeline.canvas.boundary_times, [])
            timeline.canvas.update.assert_not_called()
        finally:
            timeline.close()

    def test_scan_boundary_visible_index_culls_offscreen_work_markers(self):
        canvas = TimelineCanvas()
        try:
            rows = [
                {"timeline_sec": float(i * 2), "start": float(i * 2), "status": "pending"}
                for i in range(2000)
            ]
            canvas.scan_boundary_times = rows
            canvas._invalidate_render_cache()

            visible = canvas._visible_items_for_paint(
                canvas.scan_boundary_times,
                "scan_boundaries",
                200.0,
                206.0,
                pad_sec=0.05,
            )

            self.assertLess(len(visible), 8)
            self.assertTrue(all(199.9 <= float(item["timeline_sec"]) <= 206.1 for item in visible))
            self.assertIn("scan_boundaries", canvas._paint_index_cache)
            self.assertEqual(canvas._paint_last_visible_counts["scan_boundaries"], len(visible))
        finally:
            canvas.close()

    def test_waveform_line_groups_reuse_visible_window_cache(self):
        canvas = TimelineCanvas()
        try:
            waveform = np.zeros(1000, dtype=np.float32)
            waveform[100:260] = 0.5
            waveform[300:360] = 0.8
            canvas.set_waveform(waveform)
            canvas.pps = 100.0
            canvas.vad_segments = [{"start": 1.0, "end": 2.6}]

            first = canvas._waveform_line_groups_cached(90, 380)
            first_key = canvas._waveform_line_cache_key
            second = canvas._waveform_line_groups_cached(90, 380)

            self.assertIs(first, second)
            self.assertEqual(canvas._waveform_line_cache_key, first_key)
            self.assertGreater(sum(len(group) for group in first), 0)

            canvas.set_vad_segments([{"start": 3.0, "end": 3.6}])
            self.assertIsNone(canvas._waveform_line_cache_key)
            self.assertIsNone(canvas._waveform_line_cache)
        finally:
            canvas.close()

    def test_update_segments_reuses_gap_cache_for_same_geometry(self):
        canvas = TimelineCanvas()
        try:
            first = [
                {"start": float(i * 2), "end": float(i * 2 + 1), "text": f"first {i}", "line": i}
                for i in range(80)
            ]
            same_geometry = [
                {"start": seg["start"], "end": seg["end"], "text": f"renamed {idx}", "line": seg["line"]}
                for idx, seg in enumerate(first)
            ]

            canvas.update_segments(first, active_sec=0.0, total_dur=180.0)
            epoch_1 = canvas._render_epoch
            gap_signature = canvas._gap_segments_signature
            segment_store = canvas._segment_store
            canvas.update_segments(same_geometry, active_sec=4.0, total_dur=180.0)

            self.assertEqual(canvas._render_epoch, epoch_1)
            self.assertEqual(canvas._gap_segments_signature, gap_signature)
            self.assertIs(canvas._segment_store, segment_store)
            self.assertIs(canvas._segment_store.rows, canvas.segments)
            self.assertEqual(canvas.segments[0]["text"], "renamed 0")
            self.assertEqual(canvas.active_seg_start, 4.0)
        finally:
            canvas.close()

    def test_frame_aligned_segments_do_not_leave_micro_gap_rows(self):
        canvas = TimelineCanvas()
        try:
            canvas.set_frame_rate(30.0)
            canvas.update_segments(
                [
                    {"start": 0.0, "end": 0.999, "text": "앞", "line": 0},
                    {"start": 1.001, "end": 2.002, "text": "뒤", "line": 1},
                ],
                active_sec=0.0,
                total_dur=4.0,
            )

            self.assertAlmostEqual(canvas.segments[0]["end"], 1.0, places=6)
            self.assertAlmostEqual(canvas.segments[1]["start"], 1.0, places=6)
            internal_gaps = [
                gap for gap in list(canvas.gap_segments or [])
                if float(gap.get("start", 0.0) or 0.0) > 0.0 and float(gap.get("end", 0.0) or 0.0) < 2.1
            ]
            self.assertEqual(internal_gaps, [])
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
                seen["segments_ref"] = segments
                return [{"start": 10.0, "end": 13.0, "kind": "speech", "label": "음성", "color": "#34C759"}]

            with patch("ui.timeline.timeline_analysis.subtitle_detection_segments_for_editor", side_effect=fake_detection):
                markers = canvas.visible_voice_activity_segments_cached(
                    9.5,
                    13.5,
                    visible_segments,
                    [],
                    [],
                )
                cached_markers = canvas.visible_voice_activity_segments_cached(
                    9.5,
                    13.5,
                    visible_segments,
                    [],
                    [],
                )

            self.assertEqual(seen["segments"], visible_segments)
            self.assertIs(seen["segments_ref"], visible_segments)
            self.assertEqual(len(markers), 1)
            self.assertIs(markers, cached_markers)
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
            self.assertIsNotNone(canvas._segment_store)
            epoch = canvas._render_epoch

            canvas.set_frame_rate(24.0)

            self.assertGreater(canvas._render_epoch, epoch)
            self.assertEqual(canvas._paint_index_cache, {})
            self.assertEqual(canvas._get_fps(), 24.0)
        finally:
            canvas.close()

    def test_frame_rate_change_resnaps_existing_canvas_segments(self):
        canvas = TimelineCanvas()
        try:
            canvas.segments = [
                {"start": 1.01, "end": 2.07, "text": "fps", "line": 0},
            ]
            canvas.active_seg_start = 1.01
            canvas.playhead_sec = 2.07

            canvas.set_frame_rate(24.0)

            self.assertAlmostEqual(canvas.segments[0]["start"], canvas._snap_to_frame(1.01))
            self.assertAlmostEqual(canvas.segments[0]["end"], canvas._snap_to_frame(2.07))
            self.assertAlmostEqual(canvas.active_seg_start, canvas._snap_to_frame(1.01))
            self.assertAlmostEqual(canvas.playhead_sec, canvas._snap_to_frame(2.07))
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

    def test_scenegraph_speaker_rows_use_configured_two_speaker_names(self):
        with patch("ui.timeline.speaker_labels.load_settings", return_value={}):
            rows = build_scenegraph_subtitle_segments(
                [
                    {
                        "start": 1.0,
                        "end": 2.0,
                        "text": "대화",
                        "line": 0,
                        "speaker": "00",
                        "speaker_list": ["00", "01"],
                    },
                ],
                pps=240.0,
                fps=30.0,
                visible_start_sec=0.0,
                visible_end_sec=3.0,
                speaker_settings={
                    "spk1_id": "00",
                    "spk1_name": "인터뷰어",
                    "spk1_color": "#579DFF",
                    "spk2_id": "01",
                    "spk2_name": "게스트",
                    "spk2_color": "#75C76B",
                },
            )

        self.assertEqual([row["name"] for row in rows[0]["speakerRows"]], ["인터뷰어", "게스트"])
        self.assertEqual([row["color"] for row in rows[0]["speakerRows"]], ["#579DFF", "#75C76B"])
        self.assertEqual([row["fill"] for row in rows[0]["speakerRows"]], [
            speaker_segment_fill_hex("#579DFF"),
            speaker_segment_fill_hex("#75C76B"),
        ])
        self.assertEqual(rows[0]["speakerText"], "인터뷰어\n게스트")

    def test_scenegraph_sync_is_disabled_by_single_owner_2d_timeline(self):
        timeline = TimelineWidget()
        try:
            timeline._scenegraph_layer = _FakeScenegraphLayer()
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()
            segments = [
                {"start": float(i * 2), "end": float(i * 2 + 1), "text": f"seg {i}", "line": i, "speaker": "00"}
                for i in range(2000)
            ]
            timeline.update_segments(segments, active_sec=0.0, total_dur=5000.0)
            timeline.scroll.horizontalScrollBar().setValue(int(200.0 * float(timeline.canvas.pps)))
            self.app.processEvents()

            timeline._sync_scenegraph_layer()

            self.assertIsNone(timeline._scenegraph_layer.last_kwargs)
            self.assertFalse(timeline._scenegraph_layer.visible)
            self.assertFalse(getattr(timeline.canvas, "_scenegraph_subtitle_rendering", True))
        finally:
            timeline.close()

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

    def test_scenegraph_live_subtitle_preview_stays_in_subtitle_lane(self):
        segments = [
            {"start": 1.0, "end": 2.0, "text": "draft", "line": 0, "speaker": "00", "_live_subtitle_preview": True},
            {
                "start": 1.0,
                "end": 2.0,
                "text": "candidate",
                "line": 1,
                "speaker": "00",
                "stt_pending": True,
                "_live_stt_preview": True,
                "stt_preview_source": "STT2",
            },
        ]

        rows = build_scenegraph_subtitle_segments(
            segments,
            pps=240.0,
            fps=30.0,
            visible_start_sec=0.0,
            visible_end_sec=3.0,
        )
        by_text = {row["text"] or segments[idx]["text"]: row for idx, row in enumerate(rows)}

        self.assertEqual(by_text["draft"]["y"], SUBTITLE_TOP)
        self.assertFalse(by_text["draft"]["preview"])
        self.assertTrue(by_text["draft"]["showText"])
        self.assertEqual(by_text["candidate"]["y"], STT2_TOP + STT_PREVIEW_VERTICAL_INSET)
        self.assertTrue(by_text["candidate"]["preview"])

    def test_scenegraph_subtitle_score_label_renders_above_subtitle_segment(self):
        segments = [
            {
                "start": 1.0,
                "end": 2.0,
                "text": "needs review",
                "line": 0,
                "speaker": "00",
                "quality": {"confidence_label": "red", "confidence_score": 31},
            },
        ]

        rows = build_scenegraph_subtitle_segments(
            segments,
            pps=240.0,
            fps=30.0,
            visible_start_sec=0.0,
            visible_end_sec=3.0,
        )

        self.assertEqual(rows[0]["scoreText"], "재검사 31점")
        self.assertTrue(rows[0]["showScoreText"])
        self.assertTrue(rows[0]["showScoreSegment"])
        self.assertEqual(rows[0]["scoreY"], SCORE_TOP)
        self.assertEqual(rows[0]["scoreSegmentY"], SCORE_TOP)
        self.assertEqual(rows[0]["scoreSegmentH"], SCORE_H)
        self.assertLess(rows[0]["scoreSegmentY"] + rows[0]["scoreSegmentH"], SUBTITLE_TOP)

    def test_scenegraph_hides_subtitle_score_label_during_playback(self):
        segments = [
            {
                "start": 1.0,
                "end": 2.0,
                "text": "needs review",
                "line": 0,
                "speaker": "00",
                "quality": {"confidence_label": "red", "confidence_score": 31},
            },
        ]

        rows = build_scenegraph_subtitle_segments(
            segments,
            pps=240.0,
            fps=30.0,
            visible_start_sec=0.0,
            visible_end_sec=3.0,
            playback_active=True,
        )

        self.assertEqual(rows[0]["scoreText"], "")
        self.assertFalse(rows[0]["showScoreText"])
        self.assertFalse(rows[0]["showScoreSegment"])

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

    def test_adjacent_segment_lookup_uses_identity_position_cache(self):
        canvas = TimelineCanvas()
        try:
            canvas.segments = [
                _NoEqualitySegment({"start": float(i), "end": float(i + 0.8), "text": f"seg {i}", "line": i})
                for i in range(5000)
            ]
            canvas._invalidate_render_cache()

            target = canvas.segments[2500]
            prev_seg = canvas._get_prev_seg(target)
            next_seg = canvas._get_next_seg(target)

            self.assertIs(prev_seg, canvas.segments[2499])
            self.assertIs(next_seg, canvas.segments[2501])
            self.assertEqual(canvas._editable_segment_pos_cache[id(target)], 2500)
        finally:
            canvas.close()

    def test_drag_snap_candidates_reuse_base_cache_between_dragged_segments(self):
        canvas = TimelineCanvas()
        try:
            canvas.segments = [
                {"start": float(i), "end": float(i + 0.8), "text": f"seg {i}", "line": i}
                for i in range(5000)
            ]
            canvas.gap_segments = [{"start": 10.0, "end": 12.0}]
            canvas.vad_segments = [{"start": 15.0, "end": 16.0}]
            canvas.total_duration = 5001.0
            canvas._invalidate_render_cache()

            canvas._drag_seg = canvas.segments[10]
            canvas._drag_s0_start = canvas._drag_seg["start"]
            canvas._drag_s0_end = canvas._drag_seg["end"]
            first = canvas._drag_snap_candidates()
            base_id = id(canvas._drag_snap_base_candidates)

            canvas._drag_seg = canvas.segments[20]
            canvas._drag_s0_start = canvas._drag_seg["start"]
            canvas._drag_s0_end = canvas._drag_seg["end"]
            second = canvas._drag_snap_candidates()

            self.assertEqual(id(canvas._drag_snap_base_candidates), base_id)
            self.assertTrue(first)
            self.assertTrue(second)
            self.assertFalse(any(item.get("source") is canvas.segments[20] for item in second))
        finally:
            canvas._drag_seg = None
            canvas.close()

    def test_drag_snap_base_candidates_can_use_swift_builder(self):
        canvas = TimelineCanvas()
        try:
            canvas.segments = [
                {"start": 1.0, "end": 2.0, "text": "main", "line": 7},
            ]
            canvas.total_duration = 10.0
            canvas._invalidate_render_cache()

            with patch(
                "ui.timeline.timeline_subtitle_segment_editing.build_subtitle_drag_snap_base_via_swift",
                return_value=[
                    {"time": 1.0, "kind": "subtitle", "sourceLine": 7},
                    {"time": 10.0, "kind": "timeline"},
                ],
            ) as native_builder:
                first = canvas._build_drag_snap_base_candidates()
                second = canvas._build_drag_snap_base_candidates()

            native_builder.assert_called_once()
            self.assertEqual(first, second)
            self.assertIs(first[0].get("source"), canvas.segments[0])
            self.assertEqual(first[0].get("kind"), "subtitle")
            self.assertEqual(first[1].get("kind"), "timeline")
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
