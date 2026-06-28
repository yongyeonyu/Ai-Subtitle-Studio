import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.timeline.timeline_widget import TimelineWidget


class TimelineTimeWindowDecouplingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _make_timeline(self) -> TimelineWidget:
        timeline = TimelineWidget()
        timeline.resize(900, timeline.height())
        timeline.show()
        self.app.processEvents()
        rows = [
            {"start": 5.0, "end": 7.0, "text": "A", "line": 0},
            {"start": 60.0, "end": 64.0, "text": "B", "line": 1},
        ]
        timeline.update_segments(rows, active_sec=0.0, total_dur=180.0, fit_view=False)
        timeline.canvas.total_duration = 180.0
        timeline.global_canvas.total_duration = 180.0
        timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(180.0, timeline.canvas.pps))
        timeline.canvas.set_active(60.0)
        return timeline

    def test_fit_to_view_changes_viewport_without_rewriting_rows_or_nle_journal(self):
        timeline = self._make_timeline()
        try:
            timeline.canvas.pps = 50.0
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(180.0, 50.0))
            before_canvas_rows = [dict(row) for row in timeline.canvas.segments]
            before_global_rows = [dict(row) for row in timeline.global_canvas.segments]
            timeline.canvas.update_segments = Mock(side_effect=AssertionError("fit_to_view must not rewrite canvas rows"))
            timeline.global_canvas.update_segments = Mock(side_effect=AssertionError("fit_to_view must not rewrite global rows"))

            with patch("core.project.nle_project_state.record_nle_operation_journal_entry") as record_journal, \
                 patch("core.project.project_io.write_project_file") as write_project:
                timeline.fit_to_view()

            self.assertEqual(timeline.canvas.segments, before_canvas_rows)
            self.assertEqual(timeline.global_canvas.segments, before_global_rows)
            timeline.canvas.update_segments.assert_not_called()
            timeline.global_canvas.update_segments.assert_not_called()
            record_journal.assert_not_called()
            write_project.assert_not_called()
            self.assertTrue(timeline._fit_to_view_locked)
        finally:
            timeline.close()
            timeline.deleteLater()
            self.app.processEvents()

    def test_time_window_changes_viewport_without_rewriting_rows_or_project_state(self):
        timeline = self._make_timeline()
        try:
            before_canvas_rows = [dict(row) for row in timeline.canvas.segments]
            before_global_rows = [dict(row) for row in timeline.global_canvas.segments]
            timeline.canvas.update_segments = Mock(side_effect=AssertionError("time window must not rewrite canvas rows"))
            timeline.global_canvas.update_segments = Mock(side_effect=AssertionError("time window must not rewrite global rows"))

            with patch("core.project.nle_project_state.record_nle_operation_journal_entry") as record_journal, \
                 patch("core.project.project_io.write_project_file") as write_project:
                timeline.show_time_window_seconds(12.0, center_sec=62.0)
                timeline.show_ten_second_edit_window()

            self.assertEqual(timeline.canvas.segments, before_canvas_rows)
            self.assertEqual(timeline.global_canvas.segments, before_global_rows)
            timeline.canvas.update_segments.assert_not_called()
            timeline.global_canvas.update_segments.assert_not_called()
            record_journal.assert_not_called()
            write_project.assert_not_called()
            self.assertTrue(timeline._manual_zoom_since_fit)
            self.assertFalse(timeline._fit_to_view_locked)
        finally:
            timeline.close()
            timeline.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
