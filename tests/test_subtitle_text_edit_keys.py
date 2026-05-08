# Version: 03.10.02
# Phase: PHASE2
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

from ui.editor.subtitle_text_edit import SubtitleHighlighter, SubtitleTextEdit


class SubtitleTextEditKeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _key_event(self, key):
        return QKeyEvent(
            QKeyEvent.Type.KeyPress,
            key,
            Qt.KeyboardModifier.NoModifier,
        )

    def test_fast_left_arrow_does_not_jump_to_block_start(self):
        edit = SubtitleTextEdit()
        try:
            edit.setPlainText("abcdef")
            cursor = edit.textCursor()
            cursor.setPosition(4)
            edit.setTextCursor(cursor)

            edit.keyPressEvent(self._key_event(Qt.Key.Key_Left))
            edit.keyPressEvent(self._key_event(Qt.Key.Key_Left))

            self.assertEqual(edit.textCursor().position(), 2)
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_fast_right_arrow_does_not_jump_to_block_end(self):
        edit = SubtitleTextEdit()
        try:
            edit.setPlainText("abcdef")
            cursor = edit.textCursor()
            cursor.setPosition(2)
            edit.setTextCursor(cursor)

            edit.keyPressEvent(self._key_event(Qt.Key.Key_Right))
            edit.keyPressEvent(self._key_event(Qt.Key.Key_Right))

            self.assertEqual(edit.textCursor().position(), 4)
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_selection_lock_blocks_keyboard_cursor_movement(self):
        edit = SubtitleTextEdit()
        try:
            edit.setPlainText("abcdef")
            cursor = edit.textCursor()
            cursor.setPosition(2)
            edit.setTextCursor(cursor)
            edit.set_selection_locked(True)

            edit.keyPressEvent(self._key_event(Qt.Key.Key_Right))

            self.assertEqual(edit.textCursor().position(), 2)
            self.assertTrue(edit.isReadOnly())
            self.assertEqual(edit.focusPolicy(), Qt.FocusPolicy.NoFocus)
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_current_line_change_does_not_rehighlight_whole_document(self):
        edit = SubtitleTextEdit()
        try:
            highlighter = SubtitleHighlighter(edit.document())
            with patch.object(highlighter, "rehighlight") as rehighlight:
                highlighter.set_current_line(3)
                highlighter.set_current_line(9)
            self.assertEqual(highlighter._current_line, 9)
            rehighlight.assert_not_called()
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_quality_map_can_rehighlight_visible_blocks_only(self):
        edit = SubtitleTextEdit()
        try:
            edit.setPlainText("\n".join(f"line {idx}" for idx in range(20)))
            highlighter = SubtitleHighlighter(edit.document())
            with patch.object(highlighter, "rehighlight") as rehighlight, \
                 patch.object(highlighter, "rehighlightBlock", wraps=highlighter.rehighlightBlock) as rehighlight_block:
                highlighter.set_quality_map(
                    {5: {"confidence_label": "red"}, 6: {"confidence_label": "green"}},
                    visible_lines=range(4, 8),
                )

            rehighlight.assert_not_called()
            self.assertGreaterEqual(rehighlight_block.call_count, 2)
            self.assertEqual(set(highlighter.quality_by_line), {5, 6})
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_quick_layer_marks_qml_segment_overlay_active(self):
        edit = SubtitleTextEdit()
        try:
            edit._quick_layer = object()
            self.assertTrue(edit._quick_layer_overlay_text_active())
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_qml_text_overlay_is_opt_in_even_when_scenegraph_is_available(self):
        with patch.dict(os.environ, {"AI_SUBTITLE_EDITOR_TEXT_QML": ""}, clear=False), \
             patch("ui.editor.subtitle_text_edit.scenegraph_enabled", return_value=True):
            edit = SubtitleTextEdit()
        try:
            self.assertIsNone(edit._quick_layer)
            self.assertFalse(edit._quick_layer_overlay_text_active())
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
