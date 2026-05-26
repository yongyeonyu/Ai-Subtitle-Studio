# Version: 03.09.16
# Phase: PHASE2
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRect
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from ui.timeline.stt_preview_layout import MAX_STT_PREVIEW_SUBLANES, stt_preview_lane_geometry
from ui.timeline.timeline_constants import (
    CANVAS_H,
    FOCUS_BORDER_COLOR,
    FOCUS_BORDER_WIDTH,
    DIAMOND_Y,
    RULER_H,
    SCORE_BOT,
    SCORE_H,
    SCORE_TOP,
    SEG_BOT,
    SEG_TOP,
    SPEAKER_BOT,
    SPEAKER_TOP,
    STT1_BOT,
    STT1_TOP,
    STT2_BOT,
    STT2_TOP,
    STT_PREVIEW_LANE_H,
    STT_PREVIEW_VERTICAL_INSET,
    SUBTITLE_BOT,
    SUBTITLE_LANE_H,
    SUBTITLE_TOP,
    VOICE_ACTIVITY_BOT,
    VOICE_ACTIVITY_TOP,
    WAVE_H,
)


class TimelineLayoutConstantsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_canvas_height_allows_stt1_stt2_preview_lanes(self):
        self.assertEqual(CANVAS_H, 373)
        self.assertEqual(SEG_TOP - (RULER_H + WAVE_H), 45)
        self.assertEqual(SEG_BOT, CANVAS_H)
        self.assertGreater(SUBTITLE_TOP, RULER_H + WAVE_H)
        self.assertLess(SCORE_TOP, SUBTITLE_TOP)
        self.assertEqual(SCORE_BOT, SUBTITLE_TOP - 2)
        self.assertEqual(SCORE_H, SCORE_BOT - SCORE_TOP)
        self.assertEqual(DIAMOND_Y, SCORE_TOP + (SCORE_H // 2))
        self.assertGreater(STT1_TOP, SUBTITLE_TOP)
        self.assertEqual(STT1_BOT, STT2_TOP)
        self.assertGreater(STT2_TOP, STT1_TOP)
        self.assertLess(STT2_BOT, SPEAKER_BOT)
        self.assertEqual(SUBTITLE_BOT - SUBTITLE_TOP, SUBTITLE_LANE_H)
        self.assertEqual(STT1_BOT - STT1_TOP, STT_PREVIEW_LANE_H)
        self.assertEqual(STT2_BOT - STT2_TOP, STT_PREVIEW_LANE_H)
        self.assertGreater(STT_PREVIEW_LANE_H, SUBTITLE_LANE_H)
        self.assertEqual(SPEAKER_BOT - SPEAKER_TOP, 24)
        self.assertEqual(VOICE_ACTIVITY_BOT - VOICE_ACTIVITY_TOP, 0)
        self.assertEqual(STT_PREVIEW_VERTICAL_INSET, 2)
        self.assertEqual(SPEAKER_BOT, SEG_BOT)

    def test_stt_preview_lane_supports_three_readable_sublanes(self):
        self.assertEqual(MAX_STT_PREVIEW_SUBLANES, 3)

        _, slot_h = stt_preview_lane_geometry(
            STT1_TOP,
            STT1_BOT,
            MAX_STT_PREVIEW_SUBLANES - 1,
            MAX_STT_PREVIEW_SUBLANES,
            inset=STT_PREVIEW_VERTICAL_INSET,
        )

        self.assertGreaterEqual(slot_h, 24)

    def test_timeline_global_canvas_reaches_bottom_edge(self):
        from ui.timeline.timeline_global import MINIMAP_HEIGHT
        from ui.timeline.timeline_widget import TimelineWidget

        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.sizeHint().height() + 48)
            timeline.show()
            self.app.processEvents()

            margins = timeline.layout().contentsMargins()
            self.assertEqual(margins.top(), 0)
            self.assertEqual(margins.bottom(), 0)
            self.assertGreaterEqual(timeline.global_canvas.height(), MINIMAP_HEIGHT)
            self.assertEqual(timeline.global_canvas.geometry().bottom(), timeline.rect().bottom())
        finally:
            timeline.close()
            timeline.deleteLater()

    def test_global_canvas_subtitle_bottom_edge_spans_empty_gaps(self):
        from ui.timeline.timeline_global import (
            GLOBAL_CANVAS_CONTENT_BOTTOM_PAD,
            GLOBAL_CANVAS_VIEWPORT_BOTTOM_CLEARANCE,
            GlobalCanvas,
            MINIMAP_HEIGHT,
            MINIMAP_MARKER_LANE_H,
            MINIMAP_SUBTITLE_BORDER,
        )

        canvas = GlobalCanvas()
        try:
            canvas.resize(240, MINIMAP_HEIGHT)
            canvas.segments = [
                {"start": 0.0, "end": 0.8, "text": "left", "line": 0},
                {"start": 3.2, "end": 4.0, "text": "right", "line": 1},
            ]
            canvas.total_duration = 4.0

            image = canvas._build_static_cache().toImage()
            marker_lane_h = max(22, min(int(MINIMAP_MARKER_LANE_H), max(1, image.height() - 24)))
            bottom_lane_h = max(1, image.height() - marker_lane_h - 1 - GLOBAL_CANVAS_CONTENT_BOTTOM_PAD)
            bottom_lane = QRect(0, marker_lane_h, image.width(), bottom_lane_h)
            subtitle_lane = canvas._bottom_lane_layout(bottom_lane, include_stt=True)["SUBTITLE"]
            sample_y = max(subtitle_lane.top(), subtitle_lane.bottom() - 1)
            sample_x = image.width() // 2
            self.assertGreaterEqual(image.height() - 1 - sample_y, GLOBAL_CANVAS_CONTENT_BOTTOM_PAD)
            self.assertEqual(
                sample_y,
                image.height() - GLOBAL_CANVAS_VIEWPORT_BOTTOM_CLEARANCE,
            )

            self.assertEqual(
                QColor(image.pixel(sample_x, sample_y)).name().lower(),
                QColor(MINIMAP_SUBTITLE_BORDER).name().lower(),
            )
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_global_canvas_viewport_bottom_box_hugs_content_edge(self):
        from PyQt6.QtGui import QImage, QPainter

        from core.runtime import config
        from ui.timeline.timeline_constants import FOCUS_BORDER_WIDTH
        from ui.timeline.timeline_global import (
            GLOBAL_CANVAS_CONTENT_BOTTOM_PAD,
            GLOBAL_CANVAS_VIEWPORT_CONTENT_SEAL,
            GLOBAL_CANVAS_VIEWPORT_BOTTOM_CLEARANCE,
            GLOBAL_CANVAS_VIEWPORT_SIDE_OVERSCAN,
            GlobalCanvas,
            MINIMAP_HEIGHT,
        )

        canvas = GlobalCanvas()
        try:
            canvas.resize(240, MINIMAP_HEIGHT)
            canvas.total_duration = 10.0
            canvas.view_start = 0.0
            canvas.view_end = 1.0
            canvas.playhead_sec = -1.0
            self.assertGreaterEqual(GLOBAL_CANVAS_VIEWPORT_SIDE_OVERSCAN, 1)
            self.assertEqual(
                GLOBAL_CANVAS_VIEWPORT_BOTTOM_CLEARANCE,
                GLOBAL_CANVAS_CONTENT_BOTTOM_PAD + GLOBAL_CANVAS_VIEWPORT_CONTENT_SEAL,
            )
            self.assertGreaterEqual(GLOBAL_CANVAS_VIEWPORT_BOTTOM_CLEARANCE, FOCUS_BORDER_WIDTH * 10)
            image = QImage(canvas.size(), QImage.Format.Format_ARGB32)
            image.fill(0)
            painter = QPainter(image)
            canvas.render(painter)
            painter.end()

            bottom_y = image.height() - GLOBAL_CANVAS_VIEWPORT_BOTTOM_CLEARANCE
            sample_x = image.width() // 2
            accent = QColor(config.ACCENT).name().lower()
            for x in (0, sample_x, image.width() - 1):
                self.assertEqual(QColor(image.pixel(x, bottom_y)).name().lower(), accent)
            self.assertNotEqual(
                QColor(image.pixel(sample_x, image.height() - 1)).name().lower(),
                QColor(config.ACCENT).name().lower(),
            )
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_timeline_focus_border_uses_box_height_not_extra_bottom_line(self):
        from ui.timeline.timeline_widget import TIMELINE_FOCUS_BORDER_BOTTOM_CLEARANCE, TimelineWidget

        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.sizeHint().height() + 48)
            timeline.show()
            self.app.processEvents()
            timeline._sync_focus_border()

            border = timeline._focus_border
            clearance = timeline.rect().bottom() - border.geometry().bottom()
            self.assertEqual(TIMELINE_FOCUS_BORDER_BOTTOM_CLEARANCE, 0)
            self.assertEqual(clearance, TIMELINE_FOCUS_BORDER_BOTTOM_CLEARANCE)
        finally:
            timeline.close()
            timeline.deleteLater()

    def test_focus_border_style_is_shared_with_editor_panel(self):
        from ui.editor.editor_widget import EditorWidget

        editor = EditorWidget(
            "sample.m4a",
            [{"start": 0.0, "end": 1.0, "text": "테스트", "speaker": "00"}],
        )
        try:
            editor.show()
            self.app.processEvents()
            editor.text_edit.setFocus()
            self.app.processEvents()
            editor._sync_editor_focus_border()

            border = editor._editor_focus_border
            style = border.styleSheet()
            self.assertIn(f"border: {FOCUS_BORDER_WIDTH}px solid {FOCUS_BORDER_COLOR}", style)
            self.assertTrue(border.isVisible())
        finally:
            editor.close()


if __name__ == "__main__":
    unittest.main()
