import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from ui.editor.editor_widget import EditorWidget
from ui.timeline.timeline_constants import DIAMOND_Y, SEG_TOP


class EditorTimelineDragReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _make_editor(self, segments: list[dict]) -> EditorWidget:
        editor = EditorWidget(
            video_name="sample.mp4",
            segments=segments,
            media_path="",
            defer_media_load=True,
        )
        editor.resize(1400, 900)
        editor.show()
        self.app.processEvents()
        editor._set_editor_frame_rate(30.0)
        editor.timeline.canvas.pps = 120.0
        self.app.processEvents()
        return editor

    def _current_rows(self, editor: EditorWidget) -> list[tuple[float, float, str]]:
        rows = []
        for seg in editor._get_current_segments(force_rebuild=True):
            rows.append((float(seg["start"]), float(seg["end"]), str(seg["text"])))
        return rows

    def _drag(self, editor: EditorWidget, start: QPoint, end: QPoint) -> None:
        canvas = editor.timeline.canvas
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
        QTest.mouseMove(canvas, end, delay=5)
        self.app.processEvents()
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
        self.app.processEvents()

    def test_left_resize_without_previous_segment_persists_after_release(self):
        editor = self._make_editor([
            {"start": 1.0, "end": 2.0, "text": "현재", "speaker": "00"},
        ])
        try:
            canvas = editor.timeline.canvas
            handle_y = SEG_TOP + 32
            self._drag(
                editor,
                QPoint(canvas._x(1.0), handle_y),
                QPoint(canvas._x(0.5), handle_y),
            )

            self.assertEqual(self._current_rows(editor), [(0.5, 2.0, "현재")])
            self.assertEqual(
                [(float(seg["start"]), float(seg["end"])) for seg in canvas.segments],
                [(0.5, 2.0)],
            )
        finally:
            editor.close()

    def test_left_resize_shared_boundary_persists_for_both_segments_after_release(self):
        editor = self._make_editor([
            {"start": 0.0, "end": 1.0, "text": "앞", "speaker": "00"},
            {"start": 1.0, "end": 2.0, "text": "현재", "speaker": "00"},
        ])
        try:
            canvas = editor.timeline.canvas
            canvas.set_active(1.0)
            self.app.processEvents()
            handle_y = SEG_TOP + 32
            self._drag(
                editor,
                QPoint(canvas._x(1.0), handle_y),
                QPoint(canvas._x(0.6), handle_y),
            )

            self.assertEqual(
                self._current_rows(editor),
                [(0.0, 0.6, "앞"), (0.6, 2.0, "현재")],
            )
            self.assertEqual(
                [(float(seg["start"]), float(seg["end"])) for seg in canvas.segments],
                [(0.0, 0.6), (0.6, 2.0)],
            )
        finally:
            editor.close()

    def test_right_resize_shared_boundary_persists_for_both_segments_after_release(self):
        editor = self._make_editor([
            {"start": 1.0, "end": 2.0, "text": "현재", "speaker": "00"},
            {"start": 2.0, "end": 3.0, "text": "뒤", "speaker": "00"},
        ])
        try:
            canvas = editor.timeline.canvas
            canvas.set_active(1.0)
            self.app.processEvents()
            handle_y = SEG_TOP + 32
            self._drag(
                editor,
                QPoint(canvas._x(2.0), handle_y),
                QPoint(canvas._x(2.4), handle_y),
            )

            self.assertEqual(
                self._current_rows(editor),
                [(1.0, 2.4, "현재"), (2.4, 3.0, "뒤")],
            )
            self.assertEqual(
                [(float(seg["start"]), float(seg["end"])) for seg in canvas.segments],
                [(1.0, 2.4), (2.4, 3.0)],
            )
        finally:
            editor.close()

    def test_left_diamond_drag_persists_without_gap_after_release(self):
        editor = self._make_editor([
            {"start": 0.0, "end": 1.0, "text": "앞", "speaker": "00"},
            {"start": 1.0, "end": 2.0, "text": "현재", "speaker": "00"},
            {"start": 2.0, "end": 3.0, "text": "뒤", "speaker": "00"},
        ])
        try:
            canvas = editor.timeline.canvas
            self._drag(
                editor,
                QPoint(canvas._x(1.0), DIAMOND_Y),
                QPoint(canvas._x(0.6), DIAMOND_Y),
            )

            self.assertEqual(
                self._current_rows(editor),
                [(0.0, 0.6, "앞"), (0.6, 2.0, "현재"), (2.0, 3.0, "뒤")],
            )
            self.assertEqual(
                [(float(seg["start"]), float(seg["end"])) for seg in canvas.segments],
                [(0.0, 0.6), (0.6, 2.0), (2.0, 3.0)],
            )
        finally:
            editor.close()

    def test_right_diamond_drag_persists_without_gap_after_release(self):
        editor = self._make_editor([
            {"start": 0.0, "end": 1.0, "text": "앞", "speaker": "00"},
            {"start": 1.0, "end": 2.0, "text": "현재", "speaker": "00"},
            {"start": 2.0, "end": 3.0, "text": "뒤", "speaker": "00"},
        ])
        try:
            canvas = editor.timeline.canvas
            self._drag(
                editor,
                QPoint(canvas._x(2.0), DIAMOND_Y),
                QPoint(canvas._x(2.4), DIAMOND_Y),
            )

            self.assertEqual(
                self._current_rows(editor),
                [(0.0, 1.0, "앞"), (1.0, 2.4, "현재"), (2.4, 3.0, "뒤")],
            )
            self.assertEqual(
                [(float(seg["start"]), float(seg["end"])) for seg in canvas.segments],
                [(0.0, 1.0), (1.0, 2.4), (2.4, 3.0)],
            )
        finally:
            editor.close()


if __name__ == "__main__":
    unittest.main()
