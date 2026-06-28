import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QWidget

from ui.timeline.timeline_global import GlobalCanvas
from ui.timeline.timeline_widget import TimelineWidget


class _WheelDelta:
    def __init__(self, *, x: int = 0, y: int = 0):
        self._x = int(x)
        self._y = int(y)

    def x(self) -> int:
        return self._x

    def y(self) -> int:
        return self._y


class _WheelEvent:
    def __init__(self, *, x: int = 0, y: int = 0, modifiers=Qt.KeyboardModifier.NoModifier):
        self._delta = _WheelDelta(x=x, y=y)
        self._modifiers = modifiers
        self.accepted = False
        self.ignored = False

    def angleDelta(self):
        return self._delta

    def modifiers(self):
        return self._modifiers

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


class _GlobalWheelParent(QWidget):
    def __init__(self):
        super().__init__()
        self.apply_manual_horizontal_scroll_delta = Mock()


class TimelineWheelZoomDecouplingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_timeline_ctrl_wheel_zoom_changes_view_scale_without_model_or_nle_write(self):
        widget = TimelineWidget()
        try:
            rows = [{"start": 0.0, "end": 2.0, "text": "A", "line": 0}]
            widget.update_segments(rows, active_sec=0.0, total_dur=120.0, fit_view=False)
            widget.canvas.total_duration = 120.0
            widget.canvas.pps = 12.0
            widget.canvas.setFixedWidth(1440)
            before_rows = [dict(row) for row in widget.canvas.segments]
            before_global_rows = [dict(row) for row in widget.global_canvas.segments]
            widget.canvas.update_segments = Mock(side_effect=AssertionError("wheel zoom must not rewrite canvas segments"))
            widget.global_canvas.update_segments = Mock(side_effect=AssertionError("wheel zoom must not rewrite global segments"))

            event = _WheelEvent(y=120, modifiers=Qt.KeyboardModifier.ControlModifier)
            with patch("core.project.nle_dual_write.record_nle_operation_journal_entry") as record_journal:
                widget.wheelEvent(event)

            self.assertTrue(event.accepted)
            self.assertNotEqual(widget.canvas.pps, 12.0)
            self.assertEqual(widget.canvas.segments, before_rows)
            self.assertEqual(widget.global_canvas.segments, before_global_rows)
            widget.canvas.update_segments.assert_not_called()
            widget.global_canvas.update_segments.assert_not_called()
            record_journal.assert_not_called()
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_global_canvas_wheel_scroll_delegates_viewport_delta_without_model_or_nle_write(self):
        parent = _GlobalWheelParent()
        canvas = GlobalCanvas(parent)
        try:
            rows = [{"start": 0.0, "end": 2.0, "text": "A"}]
            canvas.update_segments(rows, 10.0)
            before_rows = [dict(row) for row in canvas.segments]
            canvas.update_segments = Mock(side_effect=AssertionError("global wheel must not rewrite segments"))

            event = _WheelEvent(y=-120)
            with patch("core.project.nle_dual_write.record_nle_operation_journal_entry") as record_journal:
                canvas.wheelEvent(event)

            self.assertTrue(event.accepted)
            parent.apply_manual_horizontal_scroll_delta.assert_called_once()
            self.assertEqual(canvas.segments, before_rows)
            canvas.update_segments.assert_not_called()
            record_journal.assert_not_called()
        finally:
            canvas.close()
            parent.close()
            canvas.deleteLater()
            parent.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
